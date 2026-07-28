"""Sale orders. Confirming an order reserves stock (held, not moved); the
delivery moves it later. Cancelling releases the reservations.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from decimal import Decimal

from app.core.deps import Principal
from app.models.party import Party
from app.modules.sales.schemas import DeliveryCreate, SaleOrderCreate
from app.services import stock_engine as eng
from app.services.numbering import allocate
from app.services.outbox import emit


class OverFulfil(Exception):
    """A delivery would move more than the sale order line ordered."""


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


# ---- delivery: the exactly-once stock-out mover ----
async def _fulfilled(session, org_id, sale_order_id, line_no) -> Decimal:
    return Decimal(
        (
            await session.execute(
                text(
                    "SELECT COALESCE(SUM(moved_qty),0) FROM stock_fulfillment "
                    "WHERE org_id=:o AND sale_order_id=:so AND sale_order_line_no=:ln"
                ),
                {"o": org_id, "so": sale_order_id, "ln": line_no},
            )
        ).scalar_one()
    )


async def get_delivery(session: AsyncSession, delivery_id: int) -> dict:
    hdr = (await session.execute(text("SELECT * FROM delivery WHERE id=:i"), {"i": delivery_id})).mappings().one()
    lines = (
        await session.execute(
            text("SELECT line_no, sale_order_line_no, product_id, godown_id, base_qty FROM delivery_line "
                 "WHERE delivery_id=:i ORDER BY line_no"),
            {"i": delivery_id},
        )
    ).mappings().all()
    return {"id": hdr["id"], "doc_no": hdr["doc_no"], "status": hdr["status"],
            "sale_order_id": hdr["sale_order_id"], "lines": [dict(r) for r in lines]}


async def create_delivery(session: AsyncSession, principal: Principal, data: DeliveryCreate) -> dict:
    order = (
        await session.execute(text("SELECT * FROM sale_order WHERE id=:i"), {"i": data.sale_order_id})
    ).mappings().one_or_none()
    if order is None:
        raise LookupError("Order not found")
    if order["status"] != "pending":
        raise ValueError(f"Order is '{order['status']}', cannot deliver")

    number = await allocate(session, principal.org_id, None, "delivery")
    delivery_id = (
        await session.execute(
            text(
                "INSERT INTO delivery (org_id, branch_id, sale_order_id, doc_no, delivery_date, delivery_boy_id, created_by) "
                "VALUES (:o,:b,:so,:no,:dd,:db,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": order["branch_id"], "so": data.sale_order_id, "no": number,
             "dd": dt.date.today(), "db": data.delivery_boy_id, "by": principal.user_id},
        )
    ).scalar_one()
    for i, line in enumerate(data.lines, start=1):
        ol = (
            await session.execute(
                text("SELECT product_id, godown_id, base_qty FROM sale_order_line WHERE order_id=:so AND line_no=:ln"),
                {"so": data.sale_order_id, "ln": line.sale_order_line_no},
            )
        ).mappings().one_or_none()
        if ol is None:
            raise ValueError(f"order line {line.sale_order_line_no} not found")
        await session.execute(
            text(
                "INSERT INTO delivery_line (org_id, delivery_id, line_no, sale_order_id, sale_order_line_no, "
                "product_id, godown_id, base_qty) VALUES (:o,:d,:ln,:so,:soln,:p,:g,:q)"
            ),
            {"o": principal.org_id, "d": delivery_id, "ln": i, "so": data.sale_order_id,
             "soln": line.sale_order_line_no, "p": ol["product_id"], "g": ol["godown_id"], "q": line.qty},
        )
    return await get_delivery(session, delivery_id)


async def dispatch_delivery(session: AsyncSession, principal: Principal, delivery_id: int) -> dict:
    d = (
        await session.execute(text("SELECT * FROM delivery WHERE id=:i FOR UPDATE"), {"i": delivery_id})
    ).mappings().one_or_none()
    if d is None:
        raise LookupError("Delivery not found")
    if d["status"] != "draft":
        raise ValueError(f"Delivery is '{d['status']}', not draft")
    eff = dt.date.today()
    lines = (
        await session.execute(
            text("SELECT line_no, sale_order_id, sale_order_line_no, product_id, godown_id, base_qty "
                 "FROM delivery_line WHERE delivery_id=:i ORDER BY line_no"),
            {"i": delivery_id},
        )
    ).mappings().all()

    for l in lines:
        ordered = Decimal(
            (await session.execute(
                text("SELECT base_qty FROM sale_order_line WHERE order_id=:so AND line_no=:ln"),
                {"so": l["sale_order_id"], "ln": l["sale_order_line_no"]})).scalar_one()
        )
        moved = await _fulfilled(session, principal.org_id, l["sale_order_id"], l["sale_order_line_no"])
        qty = Decimal(l["base_qty"])
        # THE exactly-once guard: cumulative fulfilment can never exceed the ordered qty
        if moved + qty > ordered:
            raise OverFulfil(
                f"line {l['sale_order_line_no']}: fulfilling {qty} would exceed ordered {ordered} "
                f"(already {moved})"
            )
        cost = await eng.current_wac(session, principal.org_id, l["product_id"], d["branch_id"])
        allow_neg = await eng.product_allows_negative(session, l["product_id"])
        # 1) the single stock-out for these goods
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=d["branch_id"], godown_id=l["godown_id"],
            product_id=l["product_id"], signed_qty=-qty, movement_type="sale", cost=cost,
            source=("delivery", delivery_id, l["line_no"]), effective_date=eff,
            created_by=principal.user_id, allow_negative=allow_neg,
        )
        await eng.apply_cost_outbound(session, principal.org_id, l["product_id"], d["branch_id"], qty)
        # 2) release the reservation for exactly this qty (atomic with the move)
        await eng.consume_reservation(
            session, org_id=principal.org_id, order_id=l["sale_order_id"],
            order_line_no=l["sale_order_line_no"], qty=qty,
        )
        # 3) record that this delivery moved it (the single-mover proof)
        await session.execute(
            text(
                "INSERT INTO stock_fulfillment (org_id, branch_id, sale_order_id, sale_order_line_no, "
                "moved_qty, moved_by_doc_type, moved_by_doc_id, godown_id) "
                "VALUES (:o,:b,:so,:soln,:q,'delivery',:did,:g)"
            ),
            {"o": principal.org_id, "b": d["branch_id"], "so": l["sale_order_id"],
             "soln": l["sale_order_line_no"], "q": qty, "did": delivery_id, "g": l["godown_id"]},
        )

    await session.execute(text("UPDATE delivery SET status='dispatched' WHERE id=:i"), {"i": delivery_id})
    # mark the order delivered once every line is fully fulfilled
    undelivered = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM sale_order_line sol WHERE order_id=:so AND base_qty > "
                "(SELECT COALESCE(SUM(moved_qty),0) FROM stock_fulfillment f "
                " WHERE f.sale_order_id=sol.order_id AND f.sale_order_line_no=sol.line_no)"
            ),
            {"so": d["sale_order_id"]},
        )
    ).scalar_one()
    if undelivered == 0:
        await session.execute(text("UPDATE sale_order SET status='delivered' WHERE id=:so"), {"so": d["sale_order_id"]})
    await emit(session, principal.org_id, "sale.delivery", {"delivery_id": delivery_id, "action": "dispatch"})
    return await get_delivery(session, delivery_id)


async def complete_delivery(session: AsyncSession, principal: Principal, delivery_id: int) -> dict:
    d = (await session.execute(text("SELECT status FROM delivery WHERE id=:i FOR UPDATE"), {"i": delivery_id})).mappings().one_or_none()
    if d is None:
        raise LookupError("Delivery not found")
    if d["status"] != "dispatched":
        raise ValueError(f"Delivery is '{d['status']}', not dispatched")
    await session.execute(text("UPDATE delivery SET status='delivered' WHERE id=:i"), {"i": delivery_id})
    return await get_delivery(session, delivery_id)


async def deliver_full(session: AsyncSession, principal: Principal, order_id: int, delivery_boy_id: int | None = None) -> dict:
    """Convenience: create + dispatch a delivery for all remaining qty of an order."""
    order = (await session.execute(text("SELECT * FROM sale_order WHERE id=:i"), {"i": order_id})).mappings().one_or_none()
    if order is None:
        raise LookupError("Order not found")
    if order["status"] != "pending":
        raise ValueError(f"Order is '{order['status']}', cannot deliver")
    ols = (
        await session.execute(
            text("SELECT line_no, base_qty FROM sale_order_line WHERE order_id=:i ORDER BY line_no"),
            {"i": order_id},
        )
    ).mappings().all()
    from app.modules.sales.schemas import DeliveryCreate as _DC, DeliveryLineIn as _DL
    lines = []
    for ol in ols:
        remaining = Decimal(ol["base_qty"]) - await _fulfilled(session, principal.org_id, order_id, ol["line_no"])
        if remaining > 0:
            lines.append(_DL(sale_order_line_no=ol["line_no"], qty=remaining))
    if not lines:
        raise ValueError("nothing left to deliver")
    d = await create_delivery(session, principal, _DC(sale_order_id=order_id, delivery_boy_id=delivery_boy_id, lines=lines))
    return await dispatch_delivery(session, principal, d["id"])


async def list_deliveries(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, doc_no, sale_order_id, status, delivery_date FROM delivery ORDER BY id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
