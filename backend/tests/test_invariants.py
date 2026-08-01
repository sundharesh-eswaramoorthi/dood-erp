"""Property/invariant tests — random operation sequences, real Postgres.

Asserts the ledger invariants from the Phase-2 design after fuzzed sequences:
  T1  stock_balance.on_hand == SUM(stock_movement_ledger.signed_qty)
  T2  stock_balance.reserved == SUM(active stock_reservation.qty)
  T11 party_balance.net == SUM(debit) - SUM(credit); receivable/payable split
Plus the oversell guard and the append-only trigger.
"""
from __future__ import annotations

import datetime as dt
import itertools
import random
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services import stock_engine as eng
from app.services.party_ledger import post_entry

_ids = itertools.count(1)
TODAY = dt.date(2026, 7, 29)


async def _on_hand_and_reserved(s, org, product, branch, godown):
    row = (await s.execute(text(
        "SELECT on_hand, reserved FROM stock_balance WHERE org_id=:o AND product_id=:p "
        "AND branch_id=:b AND godown_id=:g AND location_state='on_hand'"),
        {"o": org, "p": product, "b": branch, "g": godown})).mappings().first()
    return (Decimal(row["on_hand"]), Decimal(row["reserved"])) if row else (Decimal(0), Decimal(0))


async def _ledger_sum(s, org, product, branch, godown):
    return Decimal((await s.execute(text(
        "SELECT COALESCE(SUM(signed_qty),0) FROM stock_movement_ledger WHERE org_id=:o AND product_id=:p "
        "AND branch_id=:b AND godown_id=:g AND location_state='on_hand'"),
        {"o": org, "p": product, "b": branch, "g": godown})).scalar_one())


async def _active_reserved(s, org, product, branch, godown):
    return Decimal((await s.execute(text(
        "SELECT COALESCE(SUM(qty),0) FROM stock_reservation WHERE org_id=:o AND product_id=:p "
        "AND branch_id=:b AND godown_id=:g AND status='active'"),
        {"o": org, "p": product, "b": branch, "g": godown})).scalar_one())


@pytest.mark.parametrize("seed", [1, 7, 42, 1234, 99999])
async def test_stock_and_reserved_invariants(ctx, seed):
    s, org, branch, godown, product = ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"]
    rnd = random.Random(seed)
    orders: list[int] = []

    for _ in range(60):
        op = rnd.choice(["in", "in", "out", "adjust_down", "reserve", "release"])
        qty = Decimal(rnd.randint(1, 40))
        try:
            if op == "in":
                cost = Decimal(rnd.randint(20, 60))
                await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                                     signed_qty=qty, movement_type="purchase", cost=cost,
                                     source=("t_in", next(_ids), 1), effective_date=TODAY, created_by=1)
                await eng.apply_cost_inbound(s, org, product, branch, qty, cost)
            elif op in ("out", "adjust_down"):
                cost = await eng.current_wac(s, org, product, branch)
                mt = "sale" if op == "out" else "adjustment"
                await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                                     signed_qty=-qty, movement_type=mt, cost=cost,
                                     source=("t_out", next(_ids), 1), effective_date=TODAY, created_by=1)
                await eng.apply_cost_outbound(s, org, product, branch, qty)
            elif op == "reserve":
                oid = next(_ids)
                await eng.reserve_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                                        qty=qty, order_id=oid, order_line_no=1)
                orders.append(oid)
            elif op == "release" and orders:
                await eng.release_reservations(s, org_id=org, order_id=rnd.choice(orders))
            await s.commit()
        except eng.OverSell:
            await s.rollback()

    on_hand, reserved = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == await _ledger_sum(s, org, product, branch, godown), "T1: on_hand != SUM(ledger)"
    assert reserved == await _active_reserved(s, org, product, branch, godown), "T2: reserved != SUM(active)"
    assert on_hand >= 0, "no negative stock for a non-negative product"
    assert reserved >= 0
    assert on_hand - reserved >= 0, "available never negative"


@pytest.mark.parametrize("seed", [3, 11, 500])
async def test_party_ledger_invariant(ctx, seed):
    s, org, branch, party = ctx["s"], ctx["org"], ctx["branch"], ctx["party"]
    rnd = random.Random(seed)
    for _ in range(50):
        side = rnd.choice(["debit", "credit"])
        amt = Decimal(rnd.randint(1, 1000))
        await post_entry(s, org_id=org, branch_id=branch, party_id=party, entry_side=side, amount=amt,
                         source=("t_jv", next(_ids), 0), effective_date=TODAY, created_by=1)
        await s.commit()

    bal = (await s.execute(text(
        "SELECT net_balance, receivable, payable FROM party_balance WHERE org_id=:o AND party_id=:p"),
        {"o": org, "p": party})).mappings().one()
    ledger_net = Decimal((await s.execute(text(
        "SELECT SUM(CASE entry_side WHEN 'debit' THEN amount ELSE -amount END) FROM party_ledger_entry "
        "WHERE org_id=:o AND party_id=:p"), {"o": org, "p": party})).scalar_one())
    assert Decimal(bal["net_balance"]) == ledger_net, "T11: net != SUM(debit)-SUM(credit)"
    assert Decimal(bal["receivable"]) == max(ledger_net, Decimal(0))
    assert Decimal(bal["payable"]) == max(-ledger_net, Decimal(0))


async def test_oversell_guard_blocks(ctx):
    s, org, branch, godown, product = ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"]
    await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                         signed_qty=Decimal(10), movement_type="purchase", cost=Decimal(5),
                         source=("t_in", next(_ids), 1), effective_date=TODAY, created_by=1)
    await s.commit()
    with pytest.raises(eng.OverSell):
        await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                             signed_qty=Decimal(-99), movement_type="sale", cost=Decimal(5),
                             source=("t_out", next(_ids), 1), effective_date=TODAY, created_by=1)
    await s.rollback()


async def test_exactly_once_delivery(ctx):
    """T4: order -> partial deliveries -> goods move EXACTLY once; a delivery can
    never fulfil more than ordered (the single-mover / exactly-once guarantee)."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import (
        DeliveryCreate, DeliveryLineIn, OrderLineIn, SaleOrderCreate,
    )

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"]
    )
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")

    # stock in 100
    await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                         signed_qty=Decimal(100), movement_type="purchase", cost=Decimal(10),
                         source=("seed", next(_ids), 1), effective_date=TODAY, created_by=1)
    await eng.apply_cost_inbound(s, org, product, branch, Decimal(100), Decimal(10))
    await s.commit()

    # order 10 (reserves 10)
    order = await sales.create_order(s, prin, SaleOrderCreate(
        customer_id=party,
        lines=[OrderLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(10), entered_unit_id=unit, rate=Decimal(50))],
    ))
    await s.commit()
    oid = order["id"]
    on_hand, reserved = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert (on_hand, reserved) == (Decimal(100), Decimal(10))

    # two draft deliveries of 6 each (12 total > 10 ordered)
    d1 = await sales.create_delivery(s, prin, DeliveryCreate(sale_order_id=oid, lines=[DeliveryLineIn(sale_order_line_no=1, qty=Decimal(6))]))
    d2 = await sales.create_delivery(s, prin, DeliveryCreate(sale_order_id=oid, lines=[DeliveryLineIn(sale_order_line_no=1, qty=Decimal(6))]))
    await s.commit()

    # dispatch the first -> moves 6 exactly once, consumes 6 of the reservation
    await sales.dispatch_delivery(s, prin, d1["id"])
    await s.commit()
    on_hand, reserved = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == Decimal(94)   # 100 - 6
    assert reserved == Decimal(4)   # 10 - 6

    # dispatching the second (6) would make fulfilment 12 > 10 -> blocked
    with pytest.raises(sales.OverFulfil):
        await sales.dispatch_delivery(s, prin, d2["id"])
    await s.rollback()

    # nothing double-moved: total sale movements == total fulfilment == 6
    moved_out = Decimal((await s.execute(text(
        "SELECT COALESCE(-SUM(signed_qty),0) FROM stock_movement_ledger "
        "WHERE org_id=:o AND product_id=:p AND movement_type='sale'"), {"o": org, "p": product})).scalar_one())
    fulfilled = Decimal((await s.execute(text(
        "SELECT COALESCE(SUM(moved_qty),0) FROM stock_fulfillment WHERE org_id=:o AND sale_order_id=:so"),
        {"o": org, "so": oid})).scalar_one())
    assert moved_out == fulfilled == Decimal(6), "goods must move exactly once"

    # invariants still hold
    on_hand, reserved = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == await _ledger_sum(s, org, product, branch, godown)
    assert reserved == await _active_reserved(s, org, product, branch, godown)


async def _party_net(s, org, party):
    return Decimal((await s.execute(text(
        "SELECT COALESCE(net_balance,0) FROM party_balance WHERE org_id=:o AND party_id=:p"),
        {"o": org, "p": party})).scalar_one_or_none() or 0)


async def _sale_moved(s, org, product):
    return Decimal((await s.execute(text(
        "SELECT COALESCE(-SUM(signed_qty),0) FROM stock_movement_ledger "
        "WHERE org_id=:o AND product_id=:p AND movement_type='sale'"), {"o": org, "p": product})).scalar_one())


async def _prep(ctx, qty=100):
    s, org, branch, godown, product = ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"]
    await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                         signed_qty=Decimal(qty), movement_type="purchase", cost=Decimal(10),
                         source=("seed", next(_ids), 1), effective_date=TODAY, created_by=1)
    await eng.apply_cost_inbound(s, org, product, branch, Decimal(qty), Decimal(10))
    await s.commit()


async def test_bill_after_delivery_moves_no_stock(ctx):
    """Exactly-once (delivery half): once a delivery moved the goods, the bill
    posts NO stock — only the receivable + COGS. Goods move exactly once total."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import BillOrderIn, OrderLineIn, SaleOrderCreate

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx)

    order = await sales.create_order(s, prin, SaleOrderCreate(
        customer_id=party, lines=[OrderLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(20), entered_unit_id=unit, rate=Decimal(50))]))
    await s.commit()
    await sales.deliver_full(s, prin, order["id"])
    await s.commit()
    on_hand_after_delivery, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand_after_delivery == Decimal(80)  # 100 - 20

    binfo = await sales.bill_order(s, prin, order["id"], BillOrderIn())
    await s.commit()
    on_hand_after_bill, reserved = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand_after_bill == Decimal(80), "bill must NOT move already-delivered stock"
    assert all(l["moved_qty"] == 0 for l in binfo["lines"])
    # receivable posted; taxable 20*50=1000 +5%? product gst not set -> 0. grand = 1000
    assert await _party_net(s, org, party) == Decimal(binfo["grand_total"])
    # goods moved exactly once: total sale ledger == fulfilment == 20
    assert await _sale_moved(s, org, product) == Decimal(20)
    assert on_hand_after_bill == await _ledger_sum(s, org, product, branch, godown)
    assert reserved == await _active_reserved(s, org, product, branch, godown)


async def test_bill_without_delivery_is_the_mover(ctx):
    """Exactly-once (bill half): with no delivery, the bill IS the mover
    (counter-sale) — it moves the stock and records fulfilment."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import BillOrderIn, OrderLineIn, SaleOrderCreate

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx)

    order = await sales.create_order(s, prin, SaleOrderCreate(
        customer_id=party, lines=[OrderLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(15), entered_unit_id=unit, rate=Decimal(50))]))
    await s.commit()
    binfo = await sales.bill_order(s, prin, order["id"], BillOrderIn())  # no delivery -> bill moves it
    await s.commit()
    on_hand, reserved = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == Decimal(85), "bill must move stock when nothing delivered it"
    assert binfo["lines"][0]["moved_qty"] == Decimal(15)
    assert await _sale_moved(s, org, product) == Decimal(15)  # moved exactly once
    assert reserved == Decimal(0)  # reservation consumed by the bill
    assert on_hand == await _ledger_sum(s, org, product, branch, godown)
    assert reserved == await _active_reserved(s, org, product, branch, godown)


async def test_ledger_is_append_only(ctx):
    s, org, branch, godown, product = ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"]
    await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
                         signed_qty=Decimal(3), movement_type="opening", cost=Decimal(1),
                         source=("t_in", next(_ids), 1), effective_date=TODAY, created_by=1)
    await s.commit()
    with pytest.raises(Exception):
        await s.execute(text("UPDATE stock_movement_ledger SET signed_qty = 999 WHERE org_id=:o"), {"o": org})
        await s.commit()
    await s.rollback()


# ---------------------------------------------------------------------------
# v2 §3/§4 money model
# ---------------------------------------------------------------------------
async def _account_balance(s, org, account):
    return Decimal((await s.execute(text(
        "SELECT current_balance FROM cash_bank_account WHERE org_id=:o AND id=:a"),
        {"o": org, "a": account})).scalar_one())


async def _account_ledger_net(s, org, account):
    return Decimal((await s.execute(text(
        "SELECT COALESCE(SUM(CASE direction WHEN 'in' THEN amount ELSE -amount END),0) "
        "FROM account_ledger_entry WHERE org_id=:o AND account_id=:a"),
        {"o": org, "a": account})).scalar_one())


async def test_purchase_bill_money_model_reaches_the_ledger(ctx):
    """T12: line discount + overall discount + card charges + round off all
    land on the supplier's payable, and the discounted price (not the list
    price) is what enters the moving-average cost."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, PurchaseBillCreate

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")

    bill = await purchase.post_bill(s, prin, PurchaseBillCreate(
        supplier_id=party, godown_id=godown, supply_type="intra",
        discount_amount=Decimal("190"), card_charges=Decimal("10"),
        lines=[
            BillLineIn(product_id=product, entered_qty=Decimal(10), entered_unit_id=unit,
                       rate=Decimal(100), gst_rate=Decimal(5), discount_pct=Decimal(10)),
            BillLineIn(product_id=product, entered_qty=Decimal(5), entered_unit_id=unit,
                       rate=Decimal(200), gst_rate=Decimal(5)),
        ],
    ))
    await s.commit()

    # line 1: 1000 gross - 100 line disc - 90 alloc = 810 taxable, 40.50 tax
    # line 2: 1000 gross -   0 line disc - 100 alloc = 900 taxable, 45.00 tax
    assert bill["lines"][0]["taxable"] == Decimal("810.00")
    assert bill["lines"][1]["taxable"] == Decimal("900.00")
    assert bill["taxable_total"] == Decimal("1710.00")
    assert bill["tax_total"] == Decimal("85.50")
    assert bill["discount_amount"] == Decimal("190.00")
    # 1795.50 + 10 card = 1805.50 -> rounds to 1806.00
    assert bill["round_off"] == Decimal("0.50")
    assert bill["grand_total"] == Decimal("1806.00")
    assert bill["balance_amount"] == Decimal("1806.00")

    # the payable equals the invoice exactly
    assert await _party_net(s, org, party) == Decimal("-1806.00")  # credit = we owe

    # cost carried into inventory is the POST-discount taxable per base unit
    wac = await eng.current_wac(s, org, product, branch)
    # (810 + 900) / 15 units = 114.00
    assert wac.quantize(Decimal("0.01")) == Decimal("114.00")

    on_hand, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == Decimal(15)
    assert on_hand == await _ledger_sum(s, org, product, branch, godown)


async def test_paid_at_bill_time_settles_party_and_cash(ctx):
    """T13: money handed over when the invoice is raised must move BOTH the
    party balance and the cash account, or the receivable overstates reality."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import BillOrderIn, OrderLineIn, SaleOrderCreate

    s, org, branch, godown, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx)

    order = await sales.create_order(s, prin, SaleOrderCreate(
        customer_id=party,
        lines=[OrderLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(10),
                           entered_unit_id=unit, rate=Decimal(50))]))
    await s.commit()
    bill = await sales.bill_order(s, prin, order["id"], BillOrderIn(
        paid_amount=Decimal("200"), payment_account_id=account))
    await s.commit()

    assert bill["grand_total"] == Decimal("500.00")
    assert bill["paid_amount"] == Decimal("200.00")
    assert bill["balance_amount"] == Decimal("300.00")

    # receivable is the UNPAID part, not the whole invoice
    assert await _party_net(s, org, party) == Decimal("300.00")
    # the cash actually arrived, and the account invariant still holds
    assert await _account_balance(s, org, account) == Decimal("200.00")
    assert await _account_balance(s, org, account) == await _account_ledger_net(s, org, account)


async def test_multi_godown_invoice_splits_stock_per_line(ctx):
    """T14: v2's "multi godown invoice" — one bill receiving into two godowns
    must land the right qty in each, with T1 holding per godown."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, PurchaseBillCreate

    s, org, branch, g1, g2, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["godown2"],
        ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")

    await purchase.post_bill(s, prin, PurchaseBillCreate(
        supplier_id=party, godown_id=g1,
        lines=[
            BillLineIn(product_id=product, godown_id=g1, entered_qty=Decimal(10),
                       entered_unit_id=unit, rate=Decimal(10)),
            BillLineIn(product_id=product, godown_id=g2, entered_qty=Decimal(7),
                       entered_unit_id=unit, rate=Decimal(10)),
        ],
    ))
    await s.commit()

    oh1, _ = await _on_hand_and_reserved(s, org, product, branch, g1)
    oh2, _ = await _on_hand_and_reserved(s, org, product, branch, g2)
    assert oh1 == Decimal(10) and oh2 == Decimal(7)
    assert oh1 == await _ledger_sum(s, org, product, branch, g1)
    assert oh2 == await _ledger_sum(s, org, product, branch, g2)


async def test_line_godown_must_belong_to_the_branch(ctx):
    """A line can't ship goods into some other branch's godown."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, PurchaseBillCreate

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")

    other_branch = (await s.execute(
        text("INSERT INTO branch (org_id, name) VALUES (:o,'B2') RETURNING id"), {"o": org})).scalar_one()
    foreign = (await s.execute(
        text("INSERT INTO godown (org_id, branch_id, name) VALUES (:o,:b,'GX') RETURNING id"),
        {"o": org, "b": other_branch})).scalar_one()
    await s.commit()

    with pytest.raises(ValueError):
        await purchase.post_bill(s, prin, PurchaseBillCreate(
            supplier_id=party, godown_id=godown,
            lines=[BillLineIn(product_id=product, godown_id=foreign, entered_qty=Decimal(1),
                              entered_unit_id=unit, rate=Decimal(10))],
        ))
    await s.rollback()


# ---------------------------------------------------------------------------
# v2 §3 purchase orders
# ---------------------------------------------------------------------------
async def _enable_po(s, org):
    await s.execute(
        text("INSERT INTO system_setting (org_id, key, value) VALUES (:o,'feature.purchase_order',"
             "'{\"enabled\": true}'::jsonb) ON CONFLICT DO NOTHING"),
        {"o": org},
    )
    await s.commit()


async def test_po_receipt_credits_the_right_line(ctx):
    """T15: a PO may carry the SAME product on several lines (different rates,
    godowns or lots). Receipts must credit the line they name — matching on
    product_id alone credits the first one twice and the order never closes."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import POLineIn, PurchaseOrderCreate, ReceivePOIn

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _enable_po(s, org)

    po = await purchase.create_po(s, prin, PurchaseOrderCreate(
        supplier_id=party, godown_id=godown,
        lines=[
            POLineIn(product_id=product, entered_qty=Decimal(10), entered_unit_id=unit, rate=Decimal(100)),
            POLineIn(product_id=product, entered_qty=Decimal(5), entered_unit_id=unit, rate=Decimal(200)),
        ],
    ))
    await s.commit()

    result = await purchase.receive_po(s, prin, po["id"], ReceivePOIn())
    await s.commit()

    assert result["warnings"] == [], f"clean receipt should not warn: {result['warnings']}"
    after = await purchase.get_po(s, po["id"])
    assert [Decimal(l["received_qty"]) for l in after["lines"]] == [Decimal(10), Decimal(5)]
    assert after["status"] == "closed"

    # and it cannot be received a second time
    with pytest.raises(ValueError):
        await purchase.receive_po(s, prin, po["id"], ReceivePOIn())
    await s.rollback()


async def test_po_over_receipt_warns_but_allows(ctx):
    """T16: decision #10 — receiving more than ordered is a warning, not a
    block; the goods still land in stock."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, POLineIn, PurchaseOrderCreate, ReceivePOIn

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _enable_po(s, org)

    po = await purchase.create_po(s, prin, PurchaseOrderCreate(
        supplier_id=party, godown_id=godown,
        lines=[POLineIn(product_id=product, entered_qty=Decimal(10), entered_unit_id=unit, rate=Decimal(50))],
    ))
    await s.commit()

    result = await purchase.receive_po(s, prin, po["id"], ReceivePOIn(
        lines=[BillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(20),
                          entered_unit_id=unit, rate=Decimal(50), po_line_no=1)],
    ))
    await s.commit()

    assert any("tolerance" in w for w in result["warnings"]), result["warnings"]
    on_hand, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == Decimal(20), "the goods must still be received"
    assert on_hand == await _ledger_sum(s, org, product, branch, godown)


async def test_po_advance_moves_party_and_cash(ctx):
    """T17: an advance is real cash leaving before any goods arrive, so the
    supplier owes us: party DEBIT + account OUT."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import POLineIn, PurchaseOrderCreate

    s, org, branch, godown, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _enable_po(s, org)

    po = await purchase.create_po(s, prin, PurchaseOrderCreate(
        supplier_id=party, godown_id=godown,
        advance_amount=Decimal(300), payment_account_id=account,
        lines=[POLineIn(product_id=product, entered_qty=Decimal(10), entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()

    assert Decimal(po["grand_total"]) == Decimal("1000.00")
    assert Decimal(po["advance_amount"]) == Decimal("300.00")
    assert Decimal(po["balance_amount"]) == Decimal("700.00")
    # a PO moves no stock
    on_hand, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == 0
    # but the cash really left, and the supplier owes us for it
    assert await _party_net(s, org, party) == Decimal("300.00")
    assert await _account_balance(s, org, account) == Decimal("-300.00")
    assert await _account_balance(s, org, account) == await _account_ledger_net(s, org, account)


# ---------------------------------------------------------------------------
# v2 §4 counter sale (invoice with no order)
# ---------------------------------------------------------------------------
async def test_counter_sale_moves_stock_without_an_order(ctx):
    """T18: a walk-in sale has no order, so nothing reserved or delivered the
    goods — the bill is the sole mover. It must move the stock exactly once,
    write no fulfilment (that tracks ORDERS), and post the receivable."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn

    s, org, branch, g1, g2, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["godown2"],
        ctx["product"], ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")

    # stock into both godowns
    for g in (g1, g2):
        await eng.move_stock(s, org_id=org, branch_id=branch, godown_id=g, product_id=product,
                             signed_qty=Decimal(50), movement_type="purchase", cost=Decimal(10),
                             source=("seed", next(_ids), 1), effective_date=TODAY, created_by=1)
        await eng.apply_cost_inbound(s, org, product, branch, Decimal(50), Decimal(10))
    await s.commit()

    bill = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party, paid_amount=Decimal(100), payment_account_id=account,
        lines=[
            DirectBillLineIn(product_id=product, godown_id=g1, entered_qty=Decimal(3),
                             entered_unit_id=unit, rate=Decimal(100)),
            DirectBillLineIn(product_id=product, godown_id=g2, entered_qty=Decimal(2),
                             entered_unit_id=unit, rate=Decimal(150)),
        ],
    ))
    await s.commit()

    assert Decimal(bill["grand_total"]) == Decimal("600.00")
    assert Decimal(bill["balance_amount"]) == Decimal("500.00")

    # multi-godown: each line came out of its own godown
    oh1, res1 = await _on_hand_and_reserved(s, org, product, branch, g1)
    oh2, res2 = await _on_hand_and_reserved(s, org, product, branch, g2)
    assert oh1 == Decimal(47) and oh2 == Decimal(48)
    assert oh1 == await _ledger_sum(s, org, product, branch, g1)
    assert oh2 == await _ledger_sum(s, org, product, branch, g2)
    # a counter sale reserves nothing
    assert res1 == 0 and res2 == 0

    # no order, therefore no fulfilment rows
    no_order = (await s.execute(text(
        "SELECT sale_order_id FROM sales_bill WHERE id=:i"), {"i": bill["id"]})).scalar_one()
    assert no_order is None
    fulfil = (await s.execute(text(
        "SELECT COUNT(*) FROM stock_fulfillment WHERE moved_by_doc_type='sales_bill' "
        "AND moved_by_doc_id=:i"), {"i": bill["id"]})).scalar_one()
    assert fulfil == 0

    # receivable is the unpaid part; the cash arrived
    assert await _party_net(s, org, party) == Decimal("500.00")
    assert await _account_balance(s, org, account) == Decimal("100.00")
    assert await _account_balance(s, org, account) == await _account_ledger_net(s, org, account)


async def test_counter_sale_respects_the_oversell_guard(ctx):
    """A counter sale must not be a way around the stock guard."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=5)

    with pytest.raises(eng.OverSell):
        await sales.post_direct_bill(s, prin, DirectBillCreate(
            customer_id=party,
            lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(99),
                                    entered_unit_id=unit, rate=Decimal(10))],
        ))
    await s.rollback()


async def test_sale_order_is_priced_like_its_bill(ctx):
    """T19: v2 §4 — the order carries the same money block, so what the customer
    is quoted is what the invoice charges."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import BillOrderIn, OrderLineIn, SaleOrderCreate

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"], ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx)

    order = await sales.create_order(s, prin, SaleOrderCreate(
        customer_id=party, discount_pct=Decimal(10), card_charges=Decimal(5),
        lines=[OrderLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(4),
                           entered_unit_id=unit, rate=Decimal(100), gst_rate=Decimal(5))],
    ))
    await s.commit()
    # 400 gross - 10% = 360 taxable, 18 tax, 378 + 5 card = 383
    assert Decimal(order["taxable_total"]) == Decimal("360.00")
    assert Decimal(order["grand_total"]) == Decimal("383.00")

    bill = await sales.bill_order(s, prin, order["id"], BillOrderIn(
        discount_pct=Decimal(10), card_charges=Decimal(5)))
    await s.commit()
    assert Decimal(bill["grand_total"]) == Decimal(order["grand_total"])


# ---------------------------------------------------------------------------
# v2 §3 bill-wise settlement (ledger_allocation)
# ---------------------------------------------------------------------------
async def _outstanding(s, org, party, side="debit"):
    from app.services import allocation as alloc
    return {i["source_doc_id"]: Decimal(i["outstanding"])
            for i in await alloc.open_items(s, org, party, side)}


async def test_allocation_never_exceeds_either_side(ctx):
    """T20: an allocation cannot claim more than the payment has left, nor more
    than the bill still owes. Both caps are what keeps bill-wise outstanding
    reconcilable with party_balance."""
    from app.core.deps import Principal
    from app.modules.accounts import service as accounts
    from app.modules.accounts.schemas import AllocationIn, VoucherCreate
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn
    from app.services import allocation as alloc

    s, org, branch, godown, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=100)

    bill = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(5),
                                entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()
    assert Decimal(bill["grand_total"]) == Decimal("500.00")

    open_now = await alloc.open_items(s, org, party, "debit")
    entry_id = open_now[0]["entry_id"]

    # more than the bill owes
    with pytest.raises(alloc.AllocationError):
        await accounts.post_voucher(s, prin, VoucherCreate(
            party_id=party, account_id=account, voucher_type="receipt", amount=Decimal(900),
            allocations=[AllocationIn(against_entry_id=entry_id, amount=Decimal(900))],
        ))
    await s.rollback()

    # more than the payment carries
    with pytest.raises(alloc.AllocationError):
        await accounts.post_voucher(s, prin, VoucherCreate(
            party_id=party, account_id=account, voucher_type="receipt", amount=Decimal(100),
            allocations=[AllocationIn(against_entry_id=entry_id, amount=Decimal(400))],
        ))
    await s.rollback()


async def test_fifo_settles_oldest_first_and_history_reads_back(ctx):
    """T21: an unallocated receipt runs down the oldest open bills, and each
    invoice can then say what settled it (v2 §3 payment history)."""
    from app.core.deps import Principal
    from app.modules.accounts import service as accounts
    from app.modules.accounts.schemas import VoucherCreate
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn
    from app.services import allocation as alloc

    s, org, branch, godown, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=100)

    ids = []
    for qty in (2, 3):                       # 200 then 300
        b = await sales.post_direct_bill(s, prin, DirectBillCreate(
            customer_id=party,
            lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(qty),
                                    entered_unit_id=unit, rate=Decimal(100))],
        ))
        ids.append(b["id"])
    await s.commit()

    # 350 pays the first in full and part of the second
    await accounts.post_voucher(s, prin, VoucherCreate(
        party_id=party, account_id=account, voucher_type="receipt", amount=Decimal(350),
    ))
    await s.commit()

    out = await _outstanding(s, org, party)
    assert ids[0] not in out, "the oldest bill should be fully settled"
    assert out[ids[1]] == Decimal("150.00")

    hist = await alloc.document_payments(s, org, "sales_bill", ids[1])
    assert Decimal(hist["settled"]) == Decimal("150.00")
    assert Decimal(hist["outstanding"]) == Decimal("150.00")
    assert len(hist["payments"]) == 1

    # bill-wise outstanding must agree with the party balance
    total_out = sum(out.values(), Decimal(0))
    assert await _party_net(s, org, party) == total_out


async def test_paid_at_bill_time_settles_that_bill_not_the_oldest(ctx):
    """T22: cash handed over WITH an invoice belongs to that invoice. FIFO would
    put it against an older bill, which is wrong at the counter."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn
    from app.services import allocation as alloc

    s, org, branch, godown, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=100)

    old = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(2),
                                entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()
    new = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party, paid_amount=Decimal(150), payment_account_id=account,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(3),
                                entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()

    out = await _outstanding(s, org, party)
    assert out[old["id"]] == Decimal("200.00"), "the older bill must be untouched"
    assert out[new["id"]] == Decimal("150.00"), "the cash settled its own bill"
    hist = await alloc.document_payments(s, org, "sales_bill", new["id"])
    assert Decimal(hist["settled"]) == Decimal("150.00")


async def test_open_items_ignore_a_reversed_entry(ctx):
    """T23: correcting a figure leaves the superseded original in the ledger
    (append-only). It must not still read as owed."""
    from app.services import allocation as alloc
    from app.services.party_ledger import post_entry

    s, org, branch, party = ctx["s"], ctx["org"], ctx["branch"], ctx["party"]

    await post_entry(s, org_id=org, branch_id=branch, party_id=party, entry_side="debit",
                     amount=Decimal(500), source=("party_opening", party, 0),
                     effective_date=TODAY, created_by=1)
    await s.commit()
    assert len(await alloc.open_items(s, org, party, "debit")) == 1

    # correct it: reverse the 500, post 200 in its place
    await post_entry(s, org_id=org, branch_id=branch, party_id=party, entry_side="credit",
                     amount=Decimal(500), source=("party_opening", party, 0),
                     effective_date=TODAY, created_by=1,
                     entry_purpose="reversal", reversal_seq=1)
    await post_entry(s, org_id=org, branch_id=branch, party_id=party, entry_side="debit",
                     amount=Decimal(200), source=("party_opening", party, 0),
                     effective_date=TODAY, created_by=1,
                     entry_purpose="original", reversal_seq=1)
    await s.commit()

    items = await alloc.open_items(s, org, party, "debit")
    assert len(items) == 1, "only the live figure should be open"
    assert Decimal(items[0]["outstanding"]) == Decimal("200.00")
    assert await _party_net(s, org, party) == Decimal("200.00")


# ---------------------------------------------------------------------------
# v2 §7 amendment (reverse + repost, never mutate)
# ---------------------------------------------------------------------------
async def test_cancel_restores_stock_party_and_cash(ctx):
    """T24: cancelling a posted invoice must leave every ledger exactly where it
    was before the invoice existed — by posting reversals, not by deleting."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn

    s, org, branch, godown, product, party, unit, account = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"], ctx["account"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=100)

    before_stock, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    before_party = await _party_net(s, org, party)
    before_cash = await _account_balance(s, org, account)

    bill = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party, paid_amount=Decimal(200), payment_account_id=account,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(5),
                                entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()
    assert (await _on_hand_and_reserved(s, org, product, branch, godown))[0] == before_stock - 5

    await sales.cancel_bill(s, prin, bill["id"], reason="test")
    await s.commit()

    after_stock, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert after_stock == before_stock, "stock must come back"
    assert await _party_net(s, org, party) == before_party, "receivable must come back"
    assert await _account_balance(s, org, account) == before_cash, "cash must come back"

    # and it was done by APPENDING, not deleting: the originals are still there
    rows = (await s.execute(text(
        "SELECT entry_purpose, COUNT(*) c FROM stock_movement_ledger "
        "WHERE org_id=:o AND source_doc_type='sales_bill' AND source_doc_id=:i "
        "GROUP BY entry_purpose"), {"o": org, "i": bill["id"]})).mappings().all()
    purposes = {r["entry_purpose"]: r["c"] for r in rows}
    assert purposes.get("original") == 1 and purposes.get("reversal") == 1

    # the balances still equal the ledger sums
    assert after_stock == await _ledger_sum(s, org, product, branch, godown)
    assert await _account_balance(s, org, account) == await _account_ledger_net(s, org, account)

    status = (await s.execute(text("SELECT status FROM sales_bill WHERE id=:i"),
                              {"i": bill["id"]})).scalar_one()
    assert status == "cancelled"


async def test_amend_supersedes_and_nets_to_the_new_figures(ctx):
    """T25: an amendment reverses the original and posts a revision; the net
    effect is the NEW document only, and both revisions stay linked."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=100)

    before_stock, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    before_party = await _party_net(s, org, party)

    bill = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(5),
                                entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()

    new = await sales.amend_bill(s, prin, bill["id"], DirectBillCreate(
        customer_id=party,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(3),
                                entered_unit_id=unit, rate=Decimal(120))],
    ), reason="qty and rate corrected")
    await s.commit()

    # only the corrected document should be standing: 3 units, 360
    after_stock, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert after_stock == before_stock - 3
    assert await _party_net(s, org, party) == before_party + Decimal("360.00")
    assert after_stock == await _ledger_sum(s, org, product, branch, godown)

    old = (await s.execute(text("SELECT status, superseded_by FROM sales_bill WHERE id=:i"),
                           {"i": bill["id"]})).mappings().one()
    assert old["status"] == "cancelled" and old["superseded_by"] == new["id"]
    rev = (await s.execute(text("SELECT amended_from, revision_no FROM sales_bill WHERE id=:i"),
                           {"i": new["id"]})).mappings().one()
    assert rev["amended_from"] == bill["id"] and rev["revision_no"] == 2

    audit = (await s.execute(text(
        "SELECT action, replaced_by, reason FROM document_amendment "
        "WHERE doc_type='sales_bill' AND doc_id=:i"), {"i": bill["id"]})).mappings().one()
    assert audit["action"] == "amend" and audit["replaced_by"] == new["id"]


async def test_a_cancelled_document_cannot_be_amended_again(ctx):
    """T26: double-reversing would credit the party twice."""
    from app.core.deps import Principal
    from app.modules.sales import service as sales
    from app.modules.sales.schemas import DirectBillCreate, DirectBillLineIn
    from app.services import reversal

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=50)

    bill = await sales.post_direct_bill(s, prin, DirectBillCreate(
        customer_id=party,
        lines=[DirectBillLineIn(product_id=product, godown_id=godown, entered_qty=Decimal(2),
                                entered_unit_id=unit, rate=Decimal(100))],
    ))
    await s.commit()
    await sales.cancel_bill(s, prin, bill["id"], reason="first")
    await s.commit()

    with pytest.raises(reversal.NotReversible):
        await sales.cancel_bill(s, prin, bill["id"], reason="second")
    await s.rollback()


async def test_cancelling_a_purchase_bill_reverses_the_moving_average(ctx):
    """T27: reversing goods-in must take the cost back out of the WAC, or the
    valuation drifts every time a bill is corrected."""
    from app.core.deps import Principal
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, PurchaseBillCreate

    s, org, branch, godown, product, party, unit = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"],
        ctx["party"], ctx["unit"])
    prin = Principal(user_id=1, org_id=org, branch_ids=[branch], perms={"*"}, name="t")
    await _prep(ctx, qty=100)          # 100 @ 10 -> WAC 10

    wac_before = await eng.current_wac(s, org, product, branch)
    assert wac_before == Decimal("10.000000")

    bill = await purchase.post_bill(s, prin, PurchaseBillCreate(
        supplier_id=party, godown_id=godown,
        lines=[BillLineIn(product_id=product, entered_qty=Decimal(100), entered_unit_id=unit,
                          rate=Decimal(30))],
    ))
    await s.commit()
    assert await eng.current_wac(s, org, product, branch) == Decimal("20.000000")

    await purchase.cancel_bill(s, prin, bill["id"], reason="wrong supplier")
    await s.commit()

    assert await eng.current_wac(s, org, product, branch) == wac_before, "WAC must return"
    on_hand, _ = await _on_hand_and_reserved(s, org, product, branch, godown)
    assert on_hand == Decimal(100)
    assert on_hand == await _ledger_sum(s, org, product, branch, godown)
