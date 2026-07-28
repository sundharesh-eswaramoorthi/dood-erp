from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.modules.stock.schemas import AdjustmentCreate, TransferCreate, VerificationCreate
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


async def _on_hand(session, org_id, product_id, branch_id, godown_id) -> Decimal:
    val = (
        await session.execute(
            text(
                "SELECT on_hand FROM stock_balance WHERE org_id=:o AND product_id=:p "
                "AND branch_id=:b AND godown_id=:g AND location_state='on_hand'"
            ),
            {"o": org_id, "p": product_id, "b": branch_id, "g": godown_id},
        )
    ).scalar_one_or_none()
    return Decimal(val) if val is not None else Decimal(0)


# ---- transfers ----
async def get_transfer(session: AsyncSession, transfer_id: int) -> dict:
    hdr = (
        await session.execute(
            text("SELECT * FROM stock_transfer WHERE id=:i"), {"i": transfer_id}
        )
    ).mappings().one()
    lines = (
        await session.execute(
            text(
                "SELECT line_no, product_id, base_qty, unit_cost FROM stock_transfer_line "
                "WHERE transfer_id=:i ORDER BY line_no"
            ),
            {"i": transfer_id},
        )
    ).mappings().all()
    return {
        "id": hdr["id"], "doc_no": hdr["doc_no"], "status": hdr["status"],
        "from_godown_id": hdr["from_godown_id"], "to_godown_id": hdr["to_godown_id"],
        "lines": [dict(r) for r in lines],
    }


async def create_transfer(session: AsyncSession, principal: Principal, data: TransferCreate) -> dict:
    from_branch = data.from_branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    to_branch = data.to_branch_id or from_branch
    if from_branch is None:
        raise ValueError("Caller has no branch access")
    if from_branch not in principal.branch_ids:
        raise PermissionError("Source branch not permitted")
    number = await allocate(session, principal.org_id, None, "stock_transfer")
    tid = (
        await session.execute(
            text(
                "INSERT INTO stock_transfer (org_id, doc_no, from_branch_id, from_godown_id, "
                "to_branch_id, to_godown_id, created_by) VALUES (:o,:no,:fb,:fg,:tb,:tg,:by) RETURNING id"
            ),
            {"o": principal.org_id, "no": number, "fb": from_branch, "fg": data.from_godown_id,
             "tb": to_branch, "tg": data.to_godown_id, "by": principal.user_id},
        )
    ).scalar_one()
    for i, line in enumerate(data.lines, start=1):
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        await session.execute(
            text(
                "INSERT INTO stock_transfer_line (org_id, transfer_id, line_no, product_id, "
                "entered_qty, entered_unit_id, base_qty) VALUES (:o,:t,:ln,:p,:eq,:eu,:bq)"
            ),
            {"o": principal.org_id, "t": tid, "ln": i, "p": line.product_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "bq": base},
        )
    return await get_transfer(session, tid)


async def dispatch_transfer(session: AsyncSession, principal: Principal, transfer_id: int) -> dict:
    hdr = (
        await session.execute(
            text("SELECT * FROM stock_transfer WHERE id=:i FOR UPDATE"), {"i": transfer_id}
        )
    ).mappings().one_or_none()
    if hdr is None:
        raise LookupError("Transfer not found")
    if hdr["status"] != "draft":
        raise ValueError(f"Transfer is '{hdr['status']}', not draft")
    eff = dt.date.today()
    lines = (
        await session.execute(
            text("SELECT line_no, product_id, base_qty FROM stock_transfer_line WHERE transfer_id=:i ORDER BY line_no"),
            {"i": transfer_id},
        )
    ).mappings().all()
    for l in lines:
        cost = await eng.current_wac(session, principal.org_id, l["product_id"], hdr["from_branch_id"])
        allow_neg = await eng.product_allows_negative(session, l["product_id"])
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=hdr["from_branch_id"], godown_id=hdr["from_godown_id"],
            product_id=l["product_id"], signed_qty=-Decimal(l["base_qty"]), movement_type="transfer_out",
            cost=cost, source=("stock_transfer_dispatch", transfer_id, l["line_no"]),
            effective_date=eff, created_by=principal.user_id, allow_negative=allow_neg,
        )
        if hdr["from_branch_id"] != hdr["to_branch_id"]:
            await eng.apply_cost_outbound(session, principal.org_id, l["product_id"], hdr["from_branch_id"], Decimal(l["base_qty"]))
        await session.execute(
            text("UPDATE stock_transfer_line SET unit_cost=:c WHERE transfer_id=:i AND line_no=:ln"),
            {"c": cost, "i": transfer_id, "ln": l["line_no"]},
        )
    await session.execute(
        text("UPDATE stock_transfer SET status='dispatched', dispatch_date=:d WHERE id=:i"),
        {"d": eff, "i": transfer_id},
    )
    await emit(session, principal.org_id, "stock.moved", {"doc": "stock_transfer", "id": transfer_id, "action": "dispatch"})
    return await get_transfer(session, transfer_id)


async def receive_transfer(session: AsyncSession, principal: Principal, transfer_id: int) -> dict:
    hdr = (
        await session.execute(
            text("SELECT * FROM stock_transfer WHERE id=:i FOR UPDATE"), {"i": transfer_id}
        )
    ).mappings().one_or_none()
    if hdr is None:
        raise LookupError("Transfer not found")
    if hdr["status"] != "dispatched":
        raise ValueError(f"Transfer is '{hdr['status']}', not dispatched")
    eff = dt.date.today()
    lines = (
        await session.execute(
            text("SELECT line_no, product_id, base_qty, unit_cost FROM stock_transfer_line WHERE transfer_id=:i ORDER BY line_no"),
            {"i": transfer_id},
        )
    ).mappings().all()
    for l in lines:
        cost = Decimal(l["unit_cost"]) if l["unit_cost"] is not None else Decimal(0)
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=hdr["to_branch_id"], godown_id=hdr["to_godown_id"],
            product_id=l["product_id"], signed_qty=Decimal(l["base_qty"]), movement_type="transfer_in",
            cost=cost, source=("stock_transfer_receive", transfer_id, l["line_no"]),
            effective_date=eff, created_by=principal.user_id, allow_negative=True,
        )
        if hdr["from_branch_id"] != hdr["to_branch_id"]:
            await eng.apply_cost_inbound(session, principal.org_id, l["product_id"], hdr["to_branch_id"], Decimal(l["base_qty"]), cost)
    await session.execute(
        text("UPDATE stock_transfer SET status='received', receive_date=:d WHERE id=:i"),
        {"d": eff, "i": transfer_id},
    )
    await emit(session, principal.org_id, "stock.moved", {"doc": "stock_transfer", "id": transfer_id, "action": "receive"})
    return await get_transfer(session, transfer_id)


# ---- verification (snapshot-delta) ----
async def create_verification(session: AsyncSession, principal: Principal, data: VerificationCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    number = await allocate(session, principal.org_id, None, "stock_verification")
    vid = (
        await session.execute(
            text(
                "INSERT INTO stock_verification (org_id, branch_id, godown_id, doc_no, created_by) "
                "VALUES (:o,:b,:g,:no,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "g": data.godown_id, "no": number, "by": principal.user_id},
        )
    ).scalar_one()
    out = []
    for i, line in enumerate(data.lines, start=1):
        # snapshot the SYSTEM qty at the moment counting begins
        sys_qty = await _on_hand(session, principal.org_id, line.product_id, branch_id, data.godown_id)
        await session.execute(
            text(
                "INSERT INTO stock_verification_line (org_id, verification_id, line_no, product_id, "
                "system_qty_at_start, physical_qty) VALUES (:o,:v,:ln,:p,:sys,:phy)"
            ),
            {"o": principal.org_id, "v": vid, "ln": i, "p": line.product_id,
             "sys": sys_qty, "phy": line.physical_qty},
        )
        out.append({"line_no": i, "product_id": line.product_id,
                    "system_qty_at_start": sys_qty, "physical_qty": line.physical_qty, "delta": None})
    return {"id": vid, "doc_no": number, "status": "counting", "lines": out}


async def post_verification(session: AsyncSession, principal: Principal, verification_id: int) -> dict:
    hdr = (
        await session.execute(
            text("SELECT * FROM stock_verification WHERE id=:i FOR UPDATE"), {"i": verification_id}
        )
    ).mappings().one_or_none()
    if hdr is None:
        raise LookupError("Verification not found")
    if hdr["status"] != "counting":
        raise ValueError(f"Verification is '{hdr['status']}', not counting")
    lines = (
        await session.execute(
            text(
                "SELECT line_no, product_id, system_qty_at_start, physical_qty "
                "FROM stock_verification_line WHERE verification_id=:i ORDER BY line_no"
            ),
            {"i": verification_id},
        )
    ).mappings().all()
    out = []
    for l in lines:
        if l["physical_qty"] is None:
            out.append({**dict(l), "delta": None})
            continue
        # snapshot-delta: post physical - system_at_START; live moves during the count stay applied
        delta = Decimal(l["physical_qty"]) - Decimal(l["system_qty_at_start"])
        if delta != 0:
            cost = await eng.current_wac(session, principal.org_id, l["product_id"], hdr["branch_id"])
            await eng.move_stock(
                session, org_id=principal.org_id, branch_id=hdr["branch_id"], godown_id=hdr["godown_id"],
                product_id=l["product_id"], signed_qty=delta, movement_type="verification", cost=cost,
                source=("stock_verification", verification_id, l["line_no"]),
                effective_date=dt.date.today(), created_by=principal.user_id, allow_negative=True,
            )
            if delta > 0:
                await eng.apply_cost_inbound(session, principal.org_id, l["product_id"], hdr["branch_id"], delta, cost)
            else:
                await eng.apply_cost_outbound(session, principal.org_id, l["product_id"], hdr["branch_id"], -delta)
        out.append({"line_no": l["line_no"], "product_id": l["product_id"],
                    "system_qty_at_start": l["system_qty_at_start"], "physical_qty": l["physical_qty"], "delta": delta})
    await session.execute(
        text("UPDATE stock_verification SET status='posted', posted_at=now() WHERE id=:i"),
        {"i": verification_id},
    )
    await emit(session, principal.org_id, "stock.moved", {"doc": "stock_verification", "id": verification_id})
    return {"id": verification_id, "doc_no": hdr["doc_no"], "status": "posted", "lines": out}


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
