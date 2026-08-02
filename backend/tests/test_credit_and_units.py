"""V2.13: the credit limit warns instead of refusing, and a line can be entered
in a sub-unit.

Both were reachable from the API before but not from the screen — the sales page
pinned every line to the base unit, and a breached limit came back as a 409 that
stopped the sale dead.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.deps import Principal
from app.modules.products import service as products
from app.modules.products.schemas import ProductCreate
from app.modules.sales import service as sales
from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn
from app.services import credit
from app.services import stock_engine as eng


def _principal(ctx) -> Principal:
    return Principal(user_id=1, org_id=ctx["org"], branch_ids=[ctx["branch"]], perms={"*"})


async def _stock(ctx, product_id: int, qty: Decimal, cost=Decimal(10)) -> None:
    await eng.move_stock(
        ctx["s"], org_id=ctx["org"], branch_id=ctx["branch"], godown_id=ctx["godown"],
        product_id=product_id, signed_qty=qty, movement_type="purchase", cost=cost,
        source=("seed", product_id, 1), effective_date=dt.date.today(), created_by=1,
    )
    await eng.apply_cost_inbound(ctx["s"], ctx["org"], product_id, ctx["branch"], qty, cost)


async def _set_limit(ctx, amount) -> None:
    await ctx["s"].execute(
        text("UPDATE party SET credit_limit = :c WHERE id = :p"),
        {"c": amount, "p": ctx["party"]},
    )


async def test_breaching_the_limit_warns_and_still_posts(ctx):
    p = _principal(ctx)
    await _set_limit(ctx, Decimal(100))
    await _stock(ctx, ctx["product"], Decimal(50))

    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"],
        lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                entered_qty=Decimal(5), entered_unit_id=ctx["unit"],
                                rate=Decimal(100))],
    ))
    # the invoice exists and the goods moved — the limit is advice, not a gate
    assert Decimal(bill["grand_total"]) == Decimal("500.00")
    assert bill["credit_warning"] is not None
    assert "credit limit is exceeded" in bill["credit_warning"]


async def test_within_the_limit_says_nothing(ctx):
    p = _principal(ctx)
    await _set_limit(ctx, Decimal(10_000))
    await _stock(ctx, ctx["product"], Decimal(50))

    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"],
        lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                entered_qty=Decimal(5), entered_unit_id=ctx["unit"],
                                rate=Decimal(100))],
    ))
    assert bill["credit_warning"] is None


async def test_an_org_can_still_ask_for_a_hard_block(ctx):
    p = _principal(ctx)
    await _set_limit(ctx, Decimal(100))
    await _stock(ctx, ctx["product"], Decimal(50))
    await ctx["s"].execute(
        text("INSERT INTO system_setting (org_id, key, value) "
             "VALUES (:o, 'feature.credit_limit_block', '{\"enabled\": true}'::jsonb)"),
        {"o": ctx["org"]},
    )
    with pytest.raises(credit.CreditLimitExceeded):
        await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
            customer_id=ctx["party"],
            lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                    entered_qty=Decimal(5), entered_unit_id=ctx["unit"],
                                    rate=Decimal(100))],
        ))


async def test_only_the_unpaid_part_consumes_credit(ctx):
    """Cash handed over at the counter is not exposure."""
    p = _principal(ctx)
    await _set_limit(ctx, Decimal(100))
    await _stock(ctx, ctx["product"], Decimal(50))

    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"], paid_amount=Decimal(500), payment_account_id=ctx["account"],
        lines=[DirectBillLineIn(product_id=ctx["product"], godown_id=ctx["godown"],
                                entered_qty=Decimal(5), entered_unit_id=ctx["unit"],
                                rate=Decimal(100))],
    ))
    assert Decimal(bill["balance_amount"]) == Decimal("0.00")
    assert bill["credit_warning"] is None


async def test_a_product_reports_the_units_it_sells_in(ctx):
    """The line editor offers these; without them every line is stuck on base."""
    p = _principal(ctx)
    kg = (
        await ctx["s"].execute(
            text("INSERT INTO unit_of_measure (org_id, code, name) VALUES (:o,'KG','Kilogram') RETURNING id"),
            {"o": ctx["org"]},
        )
    ).scalar_one()
    prod = await products.create_product(ctx["s"], p, ProductCreate(
        code="BAG25", name="Rice 25kg", base_unit_id=ctx["unit"],
        sub_unit_id=kg, sub_unit_qty=Decimal(25),      # 1 BAG = 25 KG
    ))
    rows = await products.list_products(ctx["s"], p, q="BAG25")
    units = {u["code"]: Decimal(str(u["factor_to_base"])) for u in rows[0]["units"]}
    assert units["BAG"] == Decimal(1)
    assert units["KG"] == Decimal("0.04")             # the reciprocal of 25


async def test_selling_in_the_sub_unit_prices_per_entered_unit(ctx):
    """50 KG of a 25kg bag is 2 bags of stock, but bills as 50 x the KG rate.

    Getting this backwards is what V2.2 fixed by standardising every document on
    rate-per-entered-unit; a sub-unit line is where it shows.
    """
    p = _principal(ctx)
    kg = (
        await ctx["s"].execute(
            text("INSERT INTO unit_of_measure (org_id, code, name) VALUES (:o,'KG','Kilogram') RETURNING id"),
            {"o": ctx["org"]},
        )
    ).scalar_one()
    prod = await products.create_product(ctx["s"], p, ProductCreate(
        code="BAG25", name="Rice 25kg", base_unit_id=ctx["unit"],
        sub_unit_id=kg, sub_unit_qty=Decimal(25),
    ))
    await _stock(ctx, prod.id, Decimal(50))

    bill = await sales.post_direct_bill(ctx["s"], p, DirectBillCreate(
        customer_id=ctx["party"],
        lines=[DirectBillLineIn(product_id=prod.id, godown_id=ctx["godown"],
                                entered_qty=Decimal(50), entered_unit_id=kg,
                                rate=Decimal(30))],
    ))
    line = bill["lines"][0]
    assert Decimal(line["entered_qty"]) == Decimal(50)
    assert Decimal(line["base_qty"]) == Decimal(2)          # 50 KG = 2 bags
    assert Decimal(line["taxable"]) == Decimal("1500.00")   # 50 x 30, not 2 x 30

    on_hand = (
        await ctx["s"].execute(
            text("SELECT on_hand FROM stock_balance WHERE product_id=:p AND godown_id=:g"),
            {"p": prod.id, "g": ctx["godown"]},
        )
    ).scalar_one()
    assert Decimal(on_hand) == Decimal(48)                  # 2 bags left the shelf
