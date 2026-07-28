"""Sale orders. Confirming an order reserves stock (held, not moved); the
delivery moves it later. Cancelling releases the reservations.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.party import Party
from app.modules.sales.schemas import SaleOrderCreate
from app.services import stock_engine as eng
from app.services.numbering import allocate
from app.services.outbox import emit


async def get_order(session: AsyncSession, order_id: int) -> dict:
    hdr = (
        await session.execute(text("SELECT * FROM sale_order WHERE id=:i"), {"i": order_id})
    ).mappings().one()
    lines = (
        await session.execute(
            text("SELECT line_no, product_id, godown_id, base_qty, rate FROM sale_order_line "
                 "WHERE order_id=:i ORDER BY line_no"),
            {"i": order_id},
        )
    ).mappings().all()
    return {"id": hdr["id"], "doc_no": hdr["doc_no"], "status": hdr["status"],
            "customer_id": hdr["customer_id"], "lines": [dict(r) for r in lines]}


async def create_order(session: AsyncSession, principal: Principal, data: SaleOrderCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    customer = (await session.execute(select(Party).where(Party.id == data.customer_id))).scalar_one_or_none()
    if customer is None:
        raise ValueError("customer not found")

    number = await allocate(session, principal.org_id, None, "sale_order")
    order_id = (
        await session.execute(
            text(
                "INSERT INTO sale_order (org_id, branch_id, customer_id, doc_no, order_date, note, created_by) "
                "VALUES (:o,:b,:c,:no,:od,:nt,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "c": data.customer_id, "no": number,
             "od": data.order_date or dt.date.today(), "nt": data.note, "by": principal.user_id},
        )
    ).scalar_one()

    for i, line in enumerate(data.lines, start=1):
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        await session.execute(
            text(
                "INSERT INTO sale_order_line (org_id, order_id, line_no, product_id, godown_id, "
                "entered_qty, entered_unit_id, base_qty, rate) VALUES (:o,:ord,:ln,:p,:g,:eq,:eu,:bq,:rt)"
            ),
            {"o": principal.org_id, "ord": order_id, "ln": i, "p": line.product_id, "g": line.godown_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "bq": base, "rt": line.rate},
        )
        allow_neg = await eng.product_allows_negative(session, line.product_id)
        await eng.reserve_stock(
            session, org_id=principal.org_id, branch_id=branch_id, godown_id=line.godown_id,
            product_id=line.product_id, qty=base, order_id=order_id, order_line_no=i, allow_negative=allow_neg,
        )
    await emit(session, principal.org_id, "sale.order", {"order_id": order_id, "customer_id": data.customer_id})
    return await get_order(session, order_id)


async def cancel_order(session: AsyncSession, principal: Principal, order_id: int) -> dict:
    hdr = (
        await session.execute(text("SELECT * FROM sale_order WHERE id=:i FOR UPDATE"), {"i": order_id})
    ).mappings().one_or_none()
    if hdr is None:
        raise LookupError("Order not found")
    if hdr["status"] != "pending":
        raise ValueError(f"Order is '{hdr['status']}', cannot cancel")
    await eng.release_reservations(session, org_id=principal.org_id, order_id=order_id)
    await session.execute(text("UPDATE sale_order SET status='cancelled' WHERE id=:i"), {"i": order_id})
    await emit(session, principal.org_id, "sale.order", {"order_id": order_id, "action": "cancel"})
    return await get_order(session, order_id)


async def list_orders(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, doc_no, customer_id, order_date, status FROM sale_order ORDER BY id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
