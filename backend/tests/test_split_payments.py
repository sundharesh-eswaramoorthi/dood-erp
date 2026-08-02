"""V2.14: one document, several tenders.

Before this a document carried a single paid_amount and a single account, so
"₹1000 cash and ₹2000 by UPI" could not be recorded — the operator had to pick
one and misstate the other.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.deps import Principal
from app.modules.accounts import service as accounts
from app.modules.accounts.schemas import VoucherCreate
from app.modules.sales import service as sales
from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn
from app.modules.shared import PaymentSplitIn
from app.services import reversal
from app.services import stock_engine as eng


def _principal(ctx) -> Principal:
    return Principal(user_id=1, org_id=ctx["org"], branch_ids=[ctx["branch"]], perms={"*"})


async def _second_account(ctx) -> int:
    return (
        await ctx["s"].execute(
            text("INSERT INTO cash_bank_account (org_id, branch_id, name, account_type, "
                 "opening_balance, current_balance) VALUES (:o,:b,'HDFC','bank',0,0) RETURNING id"),
            {"o": ctx["org"], "b": ctx["branch"]},
        )
    ).scalar_one()


async def _payment_type(ctx, name: str, kind: str) -> int:
    return (
        await ctx["s"].execute(
            text("INSERT INTO payment_type (org_id, name, kind) VALUES (:o,:n,:k) RETURNING id"),
            {"o": ctx["org"], "n": name, "k": kind},
        )
    ).scalar_one()


async def _stock(ctx, qty: Decimal) -> None:
    await eng.move_stock(
        ctx["s"], org_id=ctx["org"], branch_id=ctx["branch"], godown_id=ctx["godown"],
        product_id=ctx["product"], signed_qty=qty, movement_type="purchase", cost=Decimal(10),
        source=("seed", 1, 1), effective_date=dt.date.today(), created_by=1,
    )
    await eng.apply_cost_inbound(ctx["s"], ctx["org"], ctx["product"], ctx["branch"], qty, Decimal(10))


async def _balance(ctx, account_id: int) -> Decimal:
    return Decimal(
        (
            await ctx["s"].execute(
                text("SELECT current_balance FROM cash_bank_account WHERE id=:a"), {"a": account_id}
            )
        ).scalar_one()
    )


async def test_an_invoice_can_be_settled_several_ways(ctx):
    p = _principal(ctx)
    await _stock(ctx, Decimal(50))
    hdfc = await _second_account(ctx)
    cash_t, upi_t = await _payment_type(ctx, "Cash", "cash"), await _payment_type(ctx, "UPI", "upi")

    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"],
        payments=[
            PaymentSplitIn(account_id=ctx["account"], payment_type_id=cash_t, amount=Decimal(1000)),
            PaymentSplitIn(account_id=hdfc, payment_type_id=upi_t, amount=Decimal(2000),
                           reference="UPI-9931"),
        ],
        lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                entered_qty=Decimal(3), entered_unit_id=ctx["unit"],
                                rate=Decimal(1000))],
    ))
    # paid_amount is derived from the tenders, so the balance cannot disagree
    assert Decimal(bill["paid_amount"]) == Decimal("3000.00")
    assert Decimal(bill["balance_amount"]) == Decimal("0.00")

    # the cash landed where it was said to land
    assert await _balance(ctx, ctx["account"]) == Decimal(1000)
    assert await _balance(ctx, hdfc) == Decimal(2000)

    # ...and each tender is recorded with how it was taken
    rows = (
        await ctx["s"].execute(
            text("SELECT seq, account_id, payment_type_id, amount, reference FROM document_payment "
                 "WHERE doc_type='sales_bill' AND doc_id=:i ORDER BY seq"),
            {"i": bill["id"]},
        )
    ).mappings().all()
    assert [r["seq"] for r in rows] == [0, 1]
    assert [Decimal(r["amount"]) for r in rows] == [Decimal(1000), Decimal(2000)]
    assert rows[1]["reference"] == "UPI-9931"

    # the party sees ONE settlement, not three — their statement is about debt,
    # not about which of our accounts the money reached
    party_entries = (
        await ctx["s"].execute(
            text("SELECT amount FROM party_ledger_entry WHERE org_id=:o "
                 "AND source_doc_type='sales_bill_payment' AND source_doc_id=:i"),
            {"o": ctx["org"], "i": bill["id"]},
        )
    ).scalars().all()
    assert [Decimal(a) for a in party_entries] == [Decimal(3000)]


async def test_a_split_that_disagrees_with_the_total_is_refused(ctx):
    with pytest.raises(ValueError, match="adds up to"):
        DirectBillCreate(
            customer_id=1, paid_amount=Decimal(999),
            payments=[PaymentSplitIn(account_id=1, amount=Decimal(500)),
                      PaymentSplitIn(account_id=1, amount=Decimal(1500))],
            lines=[DirectBillLineIn(product_id=1, godown_id=1, entered_qty=Decimal(1),
                                    entered_unit_id=1, rate=Decimal(1))],
        )


async def test_a_single_tender_still_works_the_old_way(ctx):
    """The one-account form is what every existing caller sends."""
    p = _principal(ctx)
    await _stock(ctx, Decimal(50))
    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"], paid_amount=Decimal(500), payment_account_id=ctx["account"],
        lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                entered_qty=Decimal(3), entered_unit_id=ctx["unit"],
                                rate=Decimal(1000))],
    ))
    assert Decimal(bill["paid_amount"]) == Decimal("500.00")
    assert await _balance(ctx, ctx["account"]) == Decimal(500)
    count = (
        await ctx["s"].execute(
            text("SELECT count(*) FROM document_payment WHERE doc_type='sales_bill' AND doc_id=:i"),
            {"i": bill["id"]},
        )
    ).scalar_one()
    assert count == 1


async def test_cancelling_takes_every_tender_back(ctx):
    p = _principal(ctx)
    await _stock(ctx, Decimal(50))
    hdfc = await _second_account(ctx)
    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"],
        payments=[PaymentSplitIn(account_id=ctx["account"], amount=Decimal(1000)),
                  PaymentSplitIn(account_id=hdfc, amount=Decimal(2000))],
        lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                entered_qty=Decimal(3), entered_unit_id=ctx["unit"],
                                rate=Decimal(1000))],
    ))
    await reversal.reverse_document(ctx["s"], p, "sales_bill", bill["id"], reason="test")

    # both accounts are back where they started — the reversal walks every leg
    assert await _balance(ctx, ctx["account"]) == Decimal(0)
    assert await _balance(ctx, hdfc) == Decimal(0)
    # and a cancelled invoice no longer claims any tender in the mode reports
    left = (
        await ctx["s"].execute(
            text("SELECT count(*) FROM document_payment WHERE doc_type='sales_bill' AND doc_id=:i"),
            {"i": bill["id"]},
        )
    ).scalar_one()
    assert left == 0


async def test_a_receipt_voucher_splits_too(ctx):
    p = _principal(ctx)
    hdfc = await _second_account(ctx)
    cheque = await _payment_type(ctx, "Cheque", "cheque")

    v = await accounts.post_voucher(ctx["s"], p, VoucherCreate(
        party_id=ctx["party"], voucher_type="receipt",
        payments=[PaymentSplitIn(account_id=ctx["account"], amount=Decimal(500)),
                  PaymentSplitIn(account_id=hdfc, payment_type_id=cheque,
                                 amount=Decimal(1500), reference="CHQ-7781")],
    ))
    assert Decimal(v["amount"]) == Decimal(2000)
    # the header keeps the first tender's account, so older reads still work
    assert v["account_id"] == ctx["account"]
    assert await _balance(ctx, ctx["account"]) == Decimal(500)
    assert await _balance(ctx, hdfc) == Decimal(1500)
    assert len(v["payments"]) == 2


async def test_an_unknown_account_is_named_not_crashed(ctx):
    """The voucher header carries the first tender, so a bad id used to reach
    the foreign key and come back as a 500 with no clue which id was wrong."""
    p = _principal(ctx)
    with pytest.raises(ValueError, match="payment account 999999 not found"):
        await accounts.post_voucher(ctx["s"], p, VoucherCreate(
            party_id=ctx["party"], voucher_type="receipt",
            payments=[PaymentSplitIn(account_id=999_999, amount=Decimal(500))],
        ))
