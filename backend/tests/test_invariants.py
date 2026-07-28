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
