from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.modules.stock.schemas import AdjustmentCreate
from app.services import stock_engine as eng
from app.services.numbering import allocate
from app.services.outbox import emit

SIGN = {"increase": 1, "opening": 1, "decrease": -1, "damage": -1, "shortage": -1}


async def post_adjustment(session: AsyncSession, principal: Principal, data: AdjustmentCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")

    eff = data.effective_date or dt.date.today()
    number = await allocate(session, principal.org_id, None, "stock_adjustment")
    adj_id = (
        await session.execute(
            text(
                "INSERT INTO stock_adjustment "
                "(org_id, branch_id, godown_id, doc_no, adj_reason, status, effective_date, note, created_by) "
                "VALUES (:o, :b, :g, :no, :r, 'posted', :ed, :note, :by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "g": data.godown_id, "no": number,
             "r": data.adj_reason, "ed": eff, "note": data.note, "by": principal.user_id},
        )
    ).scalar_one()

    sign = SIGN[data.adj_reason]
    mtype = "opening" if data.adj_reason == "opening" else "adjustment"
    out_lines = []
    for i, line in enumerate(data.lines, start=1):
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        signed = base * sign
        if sign > 0:
            if line.unit_cost is None:
                raise ValueError("unit_cost is required for increase/opening lines")
            cost = Decimal(line.unit_cost)
        else:
            cost = await eng.current_wac(session, principal.org_id, line.product_id, branch_id)

        allow_neg = await eng.product_allows_negative(session, line.product_id)
        await eng.move_stock(
            session,
            org_id=principal.org_id, branch_id=branch_id, godown_id=data.godown_id,
            product_id=line.product_id, signed_qty=signed, movement_type=mtype, cost=cost,
            source=("stock_adjustment", adj_id, i), effective_date=eff,
            created_by=principal.user_id, allow_negative=allow_neg,
        )
        if sign > 0:
            await eng.apply_cost_inbound(session, principal.org_id, line.product_id, branch_id, base, cost)
        else:
            await eng.apply_cost_outbound(session, principal.org_id, line.product_id, branch_id, base)

        await session.execute(
            text(
                "INSERT INTO stock_adjustment_line "
                "(org_id, adjustment_id, line_no, product_id, entered_qty, entered_unit_id, base_qty, unit_cost) "
                "VALUES (:o, :aid, :ln, :p, :eq, :eu, :bq, :uc)"
            ),
            {"o": principal.org_id, "aid": adj_id, "ln": i, "p": line.product_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "bq": signed, "uc": cost},
        )
        out_lines.append({"line_no": i, "product_id": line.product_id, "base_qty": signed, "unit_cost": cost})

    await emit(session, principal.org_id, "stock.moved",
               {"doc": "stock_adjustment", "id": adj_id, "branch_id": branch_id, "reason": data.adj_reason})
    return {"id": adj_id, "doc_no": number, "adj_reason": data.adj_reason, "status": "posted", "lines": out_lines}


async def current_stock(session: AsyncSession, principal: Principal, product_id: int, branch_id: int) -> dict:
    rows = (
        await session.execute(
            text(
                "SELECT godown_id, on_hand, reserved FROM stock_balance "
                "WHERE org_id = :o AND product_id = :p AND branch_id = :b AND location_state = 'on_hand' "
                "ORDER BY godown_id"
            ),
            {"o": principal.org_id, "p": product_id, "b": branch_id},
        )
    ).mappings().all()
    by_godown, on_hand, reserved = [], Decimal(0), Decimal(0)
    for r in rows:
        oh, rv = Decimal(r["on_hand"]), Decimal(r["reserved"])
        on_hand += oh
        reserved += rv
        by_godown.append({"godown_id": r["godown_id"], "on_hand": oh, "reserved": rv, "available": oh - rv})
    return {
        "product_id": product_id, "branch_id": branch_id,
        "total_on_hand": on_hand, "total_reserved": reserved, "total_available": on_hand - reserved,
        "by_godown": by_godown,
    }


async def stock_value(session: AsyncSession, principal: Principal, branch_id: int) -> dict:
    val = (
        await session.execute(
            text(
                "SELECT COALESCE(SUM(b.on_hand * COALESCE(pc.moving_avg_cost, 0)), 0) "
                "FROM stock_balance b "
                "LEFT JOIN product_cost pc ON pc.org_id = b.org_id AND pc.product_id = b.product_id "
                "AND pc.branch_id = b.branch_id "
                "WHERE b.org_id = :o AND b.branch_id = :b AND b.location_state = 'on_hand'"
            ),
            {"o": principal.org_id, "b": branch_id},
        )
    ).scalar_one()
    return {"branch_id": branch_id, "total_value": Decimal(val)}


async def list_movements(session: AsyncSession, principal: Principal, product_id: int, branch_id: int, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, godown_id, signed_qty, unit_cost, movement_type, source_doc_type, "
                "source_doc_id, effective_date FROM stock_movement_ledger "
                "WHERE org_id = :o AND product_id = :p AND branch_id = :b ORDER BY id DESC LIMIT :lim"
            ),
            {"o": principal.org_id, "p": product_id, "b": branch_id, "lim": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def reconcile(session: AsyncSession, principal: Principal) -> dict:
    """Invariant: stock_balance.on_hand == SUM(ledger.signed_qty). Should be empty."""
    drift = (
        await session.execute(
            text(
                """
                SELECT b.product_id, b.branch_id, b.godown_id, b.location_state,
                       b.on_hand, COALESCE(l.s, 0) AS ledger_sum
                FROM stock_balance b
                LEFT JOIN (
                    SELECT org_id, product_id, branch_id, godown_id, location_state, SUM(signed_qty) s
                    FROM stock_movement_ledger GROUP BY 1,2,3,4,5
                ) l ON l.org_id = b.org_id AND l.product_id = b.product_id AND l.branch_id = b.branch_id
                    AND l.godown_id = b.godown_id AND l.location_state = b.location_state
                WHERE b.on_hand <> COALESCE(l.s, 0)
                """
            )
        )
    ).mappings().all()
    return {"ok": len(drift) == 0, "drift_rows": [dict(d) for d in drift]}
