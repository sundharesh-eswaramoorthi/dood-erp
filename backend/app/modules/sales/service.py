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
from app.modules.sales.schemas import (
    DeliveryCreate,
    DirectBillCreate,
    SaleOrderCreate,
    SalesReturnCreate,
)
from app.services import credit, doc_money, money
from app.services import stock_engine as eng
from app.services.numbering import allocate
from app.services.outbox import emit
from app.services.party_ledger import post_entry as post_party_entry

Q2 = Decimal("0.01")


class OverFulfil(Exception):
    """A delivery would move more than the sale order line ordered."""


async def _product_gst(session, product_id) -> Decimal:
    v = (await session.execute(text("SELECT gst_rate FROM product WHERE id=:p"), {"p": product_id})).scalar_one_or_none()
    return Decimal(v) if v is not None else Decimal(0)


async def get_order(session: AsyncSession, order_id: int) -> dict:
    hdr = (
        await session.execute(text("SELECT * FROM sale_order WHERE id=:i"), {"i": order_id})
    ).mappings().one()
    lines = (
        await session.execute(
            text("SELECT line_no, product_id, godown_id, entered_qty, entered_unit_id, base_qty, rate, "
                 "hsn_code, remarks, gross_amount, discount_amount, header_discount_alloc, taxable, "
                 "gst_rate, cgst, sgst, igst, line_total "
                 "FROM sale_order_line WHERE order_id=:i ORDER BY line_no"),
            {"i": order_id},
        )
    ).mappings().all()
    return {**dict(hdr), "lines": [dict(r) for r in lines]}


async def _money_inputs(session: AsyncSession, lines) -> list[money.LineIn]:
    out = []
    for line in lines:
        gst = (
            Decimal(line.gst_rate)
            if getattr(line, "gst_rate", None) is not None
            else await _product_gst(session, line.product_id)
        )
        out.append(money.LineIn(
            qty=Decimal(line.entered_qty), rate=Decimal(line.rate), gst_rate=gst,
            discount_pct=Decimal(getattr(line, "discount_pct", 0) or 0),
            discount_amount=getattr(line, "discount_amount", None),
        ))
    return out


async def _post_receivable(
    session: AsyncSession,
    principal: Principal,
    *,
    bill_id: int,
    branch: int,
    customer_id: int,
    totals: money.Totals,
    cogs_total: Decimal,
    bill_date,
    payment_account_id: int | None,
) -> None:
    """The money tail every sales bill shares, whether it came from an order or
    straight off the counter. Keeping it in one place is what stops the two
    paths drifting the way purchase and sales did before v2."""
    await doc_money.write_totals(session, "sales_bill", bill_id, totals)
    await session.execute(
        text("UPDATE sales_bill SET cogs_total=:c WHERE id=:i"), {"c": cogs_total, "i": bill_id}
    )
    # only the unpaid part is real credit exposure
    await credit.check(session, principal.org_id, customer_id, totals.balance_amount)
    await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch, party_id=customer_id,
        entry_side="debit", amount=totals.grand_total, source=("sales_bill", bill_id, 0),
        effective_date=bill_date, created_by=principal.user_id,
    )
    await doc_money.settle_at_post(
        session, org_id=principal.org_id, branch_id=branch, party_id=customer_id,
        account_id=payment_account_id, doc_type="sales_bill", doc_id=bill_id,
        amount=totals.paid_amount, effective_date=bill_date, created_by=principal.user_id,
        party_side="credit", account_direction="in",
    )


async def create_order(session: AsyncSession, principal: Principal, data: SaleOrderCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    customer = (await session.execute(select(Party).where(Party.id == data.customer_id))).scalar_one_or_none()
    if customer is None:
        raise ValueError("customer not found")

    # The order is priced exactly like the bill it becomes (v2 §4).
    computed = money.compute(
        await _money_inputs(session, data.lines),
        supply_type=data.supply_type, price_mode=data.price_mode,
        header_discount_pct=data.discount_pct, header_discount_amount=data.discount_amount,
        card_charges=data.card_charges, round_off=data.round_off,
    )
    t = computed.totals
    order_date = data.order_date or dt.date.today()

    number = await allocate(session, principal.org_id, None, "sale_order")
    order_id = (
        await session.execute(
            text(
                "INSERT INTO sale_order (org_id, branch_id, customer_id, doc_no, order_date, "
                "doc_datetime, supply_type, price_mode, discount_pct, note, remarks, created_by) "
                "VALUES (:o,:b,:c,:no,:od,COALESCE(:dts, now()),:st,:pm,:dp,:nt,:rm,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "c": data.customer_id, "no": number,
             "od": order_date, "dts": data.doc_datetime, "st": data.supply_type,
             "pm": data.price_mode, "dp": data.discount_pct, "nt": data.note,
             "rm": data.remarks, "by": principal.user_id},
        )
    ).scalar_one()

    for i, (line, m) in enumerate(zip(data.lines, computed.lines), start=1):
        godown_id = await doc_money.resolve_godown(session, branch_id, line.godown_id, None)
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        hsn = line.hsn_code or await doc_money.product_hsn(session, line.product_id)
        await session.execute(
            text(
                "INSERT INTO sale_order_line (org_id, order_id, line_no, product_id, godown_id, "
                "entered_qty, entered_unit_id, base_qty, rate, hsn_code, remarks, gross_amount, "
                "discount_pct, discount_amount, header_discount_alloc, taxable, gst_rate, "
                "cgst, sgst, igst, line_total) "
                "VALUES (:o,:ord,:ln,:p,:g,:eq,:eu,:bq,:rt,:hsn,:rm,:gross,:dpct,:damt,:halloc,"
                ":tx,:gr,:cg,:sg,:ig,:lt)"
            ),
            {"o": principal.org_id, "ord": order_id, "ln": i, "p": line.product_id, "g": godown_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "bq": base, "rt": line.rate,
             "hsn": hsn, "rm": line.remarks, "gross": m.gross, "dpct": line.discount_pct or 0,
             "damt": m.discount, "halloc": m.header_discount_alloc, "tx": m.taxable,
             "gr": m.gst_rate, "cg": m.cgst, "sg": m.sgst, "ig": m.igst, "lt": m.line_total},
        )
        allow_neg = await eng.product_allows_negative(session, line.product_id)
        await eng.reserve_stock(
            session, org_id=principal.org_id, branch_id=branch_id, godown_id=godown_id,
            product_id=line.product_id, qty=base, order_id=order_id, order_line_no=i, allow_negative=allow_neg,
        )

    await session.execute(
        text(
            "UPDATE sale_order SET gross_total=:gr, line_discount_total=:ld, discount_amount=:hd, "
            "taxable_total=:tx, tax_total=:tax, card_charges=:cc, round_off=:ro, grand_total=:gt "
            "WHERE id=:i"
        ),
        {"gr": t.gross_total, "ld": t.line_discount_total, "hd": t.header_discount,
         "tx": t.taxable_total, "tax": t.tax_total, "cc": t.card_charges, "ro": t.round_off,
         "gt": t.grand_total, "i": order_id},
    )

    # v2 §1 credit limit — advisory gate at order time on the real order value;
    # the bill re-checks. Raising here rolls the whole txn back, so the
    # reservations above are undone with it.
    await credit.check(session, principal.org_id, data.customer_id, t.grand_total)

    await emit(session, principal.org_id, "sale.order",
               {"order_id": order_id, "customer_id": data.customer_id, "grand_total": str(t.grand_total)})
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


# ---- sales bill (the other half of exactly-once) ----
async def get_bill(session: AsyncSession, bill_id: int) -> dict:
    hdr = (await session.execute(text("SELECT * FROM sales_bill WHERE id=:i"), {"i": bill_id})).mappings().one()
    lines = (
        await session.execute(
            text("SELECT line_no, product_id, godown_id, entered_qty, entered_unit_id, base_qty, moved_qty, "
                 "rate, hsn_code, remarks, gross_amount, discount_amount, header_discount_alloc, taxable, "
                 "gst_rate, cgst, sgst, igst, cogs_amount, line_total "
                 "FROM sales_bill_line WHERE bill_id=:i ORDER BY line_no"),
            {"i": bill_id},
        )
    ).mappings().all()
    return {"id": hdr["id"], "doc_no": hdr["doc_no"], "status": hdr["status"],
            "customer_id": hdr["customer_id"], "supply_type": hdr["supply_type"],
            "price_mode": hdr["price_mode"], "bill_date": hdr["bill_date"],
            "doc_datetime": hdr["doc_datetime"], "cogs_total": hdr["cogs_total"],
            "gross_total": hdr["gross_total"], "line_discount_total": hdr["line_discount_total"],
            "discount_amount": hdr["discount_amount"], "taxable_total": hdr["taxable_total"],
            "tax_total": hdr["tax_total"], "card_charges": hdr["card_charges"],
            "round_off": hdr["round_off"], "grand_total": hdr["grand_total"],
            "paid_amount": hdr["paid_amount"], "balance_amount": hdr["balance_amount"],
            "lines": [dict(r) for r in lines]}


async def bill_order(
    session: AsyncSession, principal: Principal, order_id: int, opts: "BillOrderIn | None" = None
) -> dict:
    """Bill a sale order. The order supplies the lines (each with its own
    godown, hence multi-godown invoices) AND its agreed prices; `opts` may
    override the header money block.

    What the order quoted is what the invoice charges: line GST and discounts
    come off the order line, and any header money field the caller did not
    explicitly set falls back to the order's. Re-deriving GST from the product
    instead would silently re-price an order whenever the product master
    changed after it was taken.

    Stock rule is unchanged (decision #5): the bill moves only what a delivery
    has not already moved.
    """
    from app.modules.sales.schemas import BillOrderIn  # local: avoids a cycle

    opts = opts or BillOrderIn()
    sent = opts.model_fields_set
    order = (await session.execute(text("SELECT * FROM sale_order WHERE id=:i"), {"i": order_id})).mappings().one_or_none()
    if order is None:
        raise LookupError("Order not found")
    if order["status"] == "cancelled":
        raise ValueError("Order is cancelled")
    branch = order["branch_id"]
    bill_date = dt.date.today()

    lines = (
        await session.execute(
            text("SELECT line_no, product_id, godown_id, entered_qty, entered_unit_id, base_qty, rate, "
                 "gst_rate, discount_pct, discount_amount "
                 "FROM sale_order_line WHERE order_id=:i ORDER BY line_no"),
            {"i": order_id},
        )
    ).mappings().all()

    # the order's own figures, unless the caller deliberately overrode them
    supply_type = opts.supply_type if "supply_type" in sent else order["supply_type"]
    price_mode = opts.price_mode if "price_mode" in sent else order["price_mode"]
    header_pct = opts.discount_pct if "discount_pct" in sent else Decimal(order["discount_pct"])
    header_amt = (
        opts.discount_amount if "discount_amount" in sent
        else (Decimal(order["discount_amount"]) or None) or None
    )
    card = opts.card_charges if "card_charges" in sent else Decimal(order["card_charges"])

    money_lines = [
        money.LineIn(
            qty=Decimal(l["entered_qty"]), rate=Decimal(l["rate"]),
            gst_rate=Decimal(l["gst_rate"]),
            discount_pct=Decimal(l["discount_pct"] or 0),
            discount_amount=Decimal(l["discount_amount"]) if l["discount_amount"] else None,
        )
        for l in lines
    ]
    computed = money.compute(
        money_lines,
        supply_type=supply_type, price_mode=price_mode,
        header_discount_pct=header_pct, header_discount_amount=header_amt,
        card_charges=card, round_off=opts.round_off, paid_amount=opts.paid_amount,
    )
    t = computed.totals

    number = await allocate(session, principal.org_id, None, "sales_bill")
    bill_id = (
        await session.execute(
            text("INSERT INTO sales_bill (org_id, branch_id, customer_id, sale_order_id, doc_no, supply_type, "
                 "price_mode, bill_date, doc_datetime, discount_pct, remarks, payment_account_id, created_by) "
                 "VALUES (:o,:b,:c,:so,:no,:st,:pm,:bd,COALESCE(:dts, now()),:dp,:rm,:pa,:by) RETURNING id"),
            {"o": principal.org_id, "b": branch, "c": order["customer_id"], "so": order_id, "no": number,
             "st": supply_type, "pm": price_mode, "bd": bill_date, "dts": opts.doc_datetime,
             "dp": header_pct, "rm": opts.remarks, "pa": opts.payment_account_id,
             "by": principal.user_id},
        )
    ).scalar_one()

    cogs_total = Decimal(0)
    out = []
    for l, m in zip(lines, computed.lines):
        ordered = Decimal(l["base_qty"])
        fulfilled = await _fulfilled(session, principal.org_id, order_id, l["line_no"])
        to_move = ordered - fulfilled  # the bill moves ONLY what a delivery hasn't
        moved = Decimal(0)
        if to_move > 0:
            cost = await eng.current_wac(session, principal.org_id, l["product_id"], branch)
            allow_neg = await eng.product_allows_negative(session, l["product_id"])
            await eng.move_stock(
                session, org_id=principal.org_id, branch_id=branch, godown_id=l["godown_id"],
                product_id=l["product_id"], signed_qty=-to_move, movement_type="sale", cost=cost,
                source=("sales_bill", bill_id, l["line_no"]), effective_date=bill_date,
                created_by=principal.user_id, allow_negative=allow_neg,
            )
            await eng.apply_cost_outbound(session, principal.org_id, l["product_id"], branch, to_move)
            await eng.consume_reservation(session, org_id=principal.org_id, order_id=order_id,
                                          order_line_no=l["line_no"], qty=to_move)
            await session.execute(
                text("INSERT INTO stock_fulfillment (org_id, branch_id, sale_order_id, sale_order_line_no, "
                     "moved_qty, moved_by_doc_type, moved_by_doc_id, godown_id) "
                     "VALUES (:o,:b,:so,:ln,:q,'sales_bill',:bid,:g)"),
                {"o": principal.org_id, "b": branch, "so": order_id, "ln": l["line_no"],
                 "q": to_move, "bid": bill_id, "g": l["godown_id"]},
            )
            moved = to_move

        cogs_unit = await eng.current_wac(session, principal.org_id, l["product_id"], branch)
        cogs = (cogs_unit * ordered).quantize(Q2)
        hsn = await doc_money.product_hsn(session, l["product_id"])
        await session.execute(
            text("INSERT INTO sales_bill_line (org_id, bill_id, line_no, product_id, godown_id, entered_qty, "
                 "entered_unit_id, base_qty, moved_qty, rate, hsn_code, gross_amount, discount_amount, "
                 "header_discount_alloc, taxable, gst_rate, cgst, sgst, igst, cogs_amount, line_total) "
                 "VALUES (:o,:bid,:ln,:p,:g,:eq,:eu,:bq,:mv,:rt,:hsn,:gross,:damt,:halloc,"
                 ":tx,:gr,:cg,:sg,:ig,:cogs,:lt)"),
            {"o": principal.org_id, "bid": bill_id, "ln": l["line_no"], "p": l["product_id"],
             "g": l["godown_id"], "eq": l["entered_qty"], "eu": l["entered_unit_id"], "bq": ordered,
             "mv": moved, "rt": l["rate"], "hsn": hsn, "gross": m.gross, "damt": m.discount,
             "halloc": m.header_discount_alloc, "tx": m.taxable, "gr": m.gst_rate, "cg": m.cgst,
             "sg": m.sgst, "ig": m.igst, "cogs": cogs, "lt": m.line_total},
        )
        cogs_total += cogs
        out.append({"line_no": l["line_no"], "product_id": l["product_id"], "godown_id": l["godown_id"],
                    "entered_qty": l["entered_qty"], "entered_unit_id": l["entered_unit_id"],
                    "base_qty": ordered, "moved_qty": moved, "rate": l["rate"], "hsn_code": hsn,
                    "gross_amount": m.gross, "discount_amount": m.discount,
                    "header_discount_alloc": m.header_discount_alloc, "taxable": m.taxable,
                    "gst_rate": m.gst_rate, "cgst": m.cgst, "sgst": m.sgst, "igst": m.igst,
                    "cogs_amount": cogs, "line_total": m.line_total})

    await _post_receivable(
        session, principal, bill_id=bill_id, branch=branch, customer_id=order["customer_id"],
        totals=t, cogs_total=cogs_total, bill_date=bill_date,
        payment_account_id=opts.payment_account_id,
    )
    # order fully fulfilled now?
    undelivered = (
        await session.execute(
            text("SELECT COUNT(*) FROM sale_order_line sol WHERE order_id=:so AND base_qty > "
                 "(SELECT COALESCE(SUM(moved_qty),0) FROM stock_fulfillment f "
                 " WHERE f.sale_order_id=sol.order_id AND f.sale_order_line_no=sol.line_no)"),
            {"so": order_id},
        )
    ).scalar_one()
    if undelivered == 0 and order["status"] == "pending":
        await session.execute(text("UPDATE sale_order SET status='delivered' WHERE id=:i"), {"i": order_id})
    await emit(session, principal.org_id, "sale.bill",
               {"bill_id": bill_id, "order_id": order_id, "grand_total": str(t.grand_total)})
    return await get_bill(session, bill_id)


async def post_direct_bill(
    session: AsyncSession, principal: Principal, data: "DirectBillCreate"
) -> dict:
    """v2 §4: a sale invoice with no order behind it (counter / walk-in sale).

    With no order there is no reservation to consume and no delivery, so the
    bill is the sole mover — the same rule decision #5 already applies when a
    bill runs ahead of its delivery. Nothing is written to stock_fulfillment
    either: that table tracks how much of an ORDER has been satisfied, and there
    is no order here.
    """
    branch = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch is None:
        raise ValueError("Caller has no branch access")
    if branch not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    customer = (await session.execute(select(Party).where(Party.id == data.customer_id))).scalar_one_or_none()
    if customer is None:
        raise ValueError("customer not found")

    bill_date = data.bill_date or dt.date.today()
    computed = money.compute(
        await _money_inputs(session, data.lines),
        supply_type=data.supply_type, price_mode=data.price_mode,
        header_discount_pct=data.discount_pct, header_discount_amount=data.discount_amount,
        card_charges=data.card_charges, round_off=data.round_off, paid_amount=data.paid_amount,
    )
    t = computed.totals

    number = await allocate(session, principal.org_id, None, "sales_bill")
    bill_id = (
        await session.execute(
            text("INSERT INTO sales_bill (org_id, branch_id, customer_id, sale_order_id, doc_no, "
                 "supply_type, price_mode, bill_date, doc_datetime, discount_pct, remarks, "
                 "payment_account_id, created_by) "
                 "VALUES (:o,:b,:c,NULL,:no,:st,:pm,:bd,COALESCE(:dts, now()),:dp,:rm,:pa,:by) RETURNING id"),
            {"o": principal.org_id, "b": branch, "c": data.customer_id, "no": number,
             "st": data.supply_type, "pm": data.price_mode, "bd": bill_date,
             "dts": data.doc_datetime, "dp": data.discount_pct, "rm": data.remarks,
             "pa": data.payment_account_id, "by": principal.user_id},
        )
    ).scalar_one()

    cogs_total = Decimal(0)
    out = []
    for i, (line, m) in enumerate(zip(data.lines, computed.lines), start=1):
        godown_id = await doc_money.resolve_godown(session, branch, line.godown_id, None)
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        hsn = line.hsn_code or await doc_money.product_hsn(session, line.product_id)
        cost = await eng.current_wac(session, principal.org_id, line.product_id, branch)
        allow_neg = await eng.product_allows_negative(session, line.product_id)

        # the bill IS the mover here
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=branch, godown_id=godown_id,
            product_id=line.product_id, signed_qty=-base, movement_type="sale", cost=cost,
            source=("sales_bill", bill_id, i), effective_date=bill_date,
            created_by=principal.user_id, allow_negative=allow_neg,
        )
        await eng.apply_cost_outbound(session, principal.org_id, line.product_id, branch, base)
        cogs = (cost * base).quantize(Q2)

        await session.execute(
            text("INSERT INTO sales_bill_line (org_id, bill_id, line_no, product_id, godown_id, "
                 "entered_qty, entered_unit_id, base_qty, moved_qty, rate, hsn_code, remarks, "
                 "gross_amount, discount_pct, discount_amount, header_discount_alloc, taxable, "
                 "gst_rate, cgst, sgst, igst, cogs_amount, line_total) "
                 "VALUES (:o,:bid,:ln,:p,:g,:eq,:eu,:bq,:mv,:rt,:hsn,:rm,:gross,:dpct,:damt,:halloc,"
                 ":tx,:gr,:cg,:sg,:ig,:cogs,:lt)"),
            {"o": principal.org_id, "bid": bill_id, "ln": i, "p": line.product_id, "g": godown_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "bq": base, "mv": base,
             "rt": line.rate, "hsn": hsn, "rm": line.remarks, "gross": m.gross,
             "dpct": line.discount_pct or 0, "damt": m.discount,
             "halloc": m.header_discount_alloc, "tx": m.taxable, "gr": m.gst_rate,
             "cg": m.cgst, "sg": m.sgst, "ig": m.igst, "cogs": cogs, "lt": m.line_total},
        )
        cogs_total += cogs
        out.append({"line_no": i, "product_id": line.product_id, "godown_id": godown_id,
                    "entered_qty": line.entered_qty, "entered_unit_id": line.entered_unit_id,
                    "base_qty": base, "moved_qty": base, "rate": line.rate, "hsn_code": hsn,
                    "remarks": line.remarks, "gross_amount": m.gross,
                    "discount_amount": m.discount, "header_discount_alloc": m.header_discount_alloc,
                    "taxable": m.taxable, "gst_rate": m.gst_rate, "cgst": m.cgst, "sgst": m.sgst,
                    "igst": m.igst, "cogs_amount": cogs, "line_total": m.line_total})

    await _post_receivable(
        session, principal, bill_id=bill_id, branch=branch, customer_id=data.customer_id,
        totals=t, cogs_total=cogs_total, bill_date=bill_date,
        payment_account_id=data.payment_account_id,
    )
    await emit(session, principal.org_id, "sale.bill",
               {"bill_id": bill_id, "order_id": None, "counter_sale": True,
                "grand_total": str(t.grand_total)})
    return await get_bill(session, bill_id)


async def list_bills(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, doc_no, customer_id, sale_order_id, grand_total, paid_amount, "
                 "balance_amount, bill_date, status FROM sales_bill ORDER BY id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    # money as decimal strings, like the documents themselves
    m = ("grand_total", "paid_amount", "balance_amount")
    return [{k: (str(v) if k in m and v is not None else v) for k, v in r.items()} for r in rows]


async def post_sales_return(session: AsyncSession, principal: Principal, data: SalesReturnCreate) -> dict:
    branch = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch is None:
        raise ValueError("Caller has no branch access")
    if branch not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    customer = (await session.execute(select(Party).where(Party.id == data.customer_id))).scalar_one_or_none()
    if customer is None:
        raise ValueError("customer not found")

    rdate = data.return_date or dt.date.today()
    money_lines = []
    for line in data.lines:
        gst = (
            Decimal(line.gst_rate)
            if line.gst_rate is not None
            else await _product_gst(session, line.product_id)
        )
        money_lines.append(money.LineIn(
            qty=Decimal(line.entered_qty), rate=Decimal(line.rate), gst_rate=gst,
            discount_pct=Decimal(line.discount_pct or 0), discount_amount=line.discount_amount,
        ))
    computed = money.compute(
        money_lines,
        supply_type=data.supply_type, price_mode=data.price_mode,
        header_discount_pct=data.discount_pct, header_discount_amount=data.discount_amount,
        card_charges=data.card_charges, round_off=data.round_off, paid_amount=data.paid_amount,
    )
    t = computed.totals

    number = await allocate(session, principal.org_id, None, "sales_return")
    ret_id = (
        await session.execute(
            text("INSERT INTO sales_return (org_id, branch_id, customer_id, godown_id, doc_no, orig_bill_id, "
                 "supply_type, price_mode, return_date, doc_datetime, discount_pct, remarks, "
                 "payment_account_id, created_by) "
                 "VALUES (:o,:b,:c,:g,:no,:ob,:st,:pm,:rd,COALESCE(:dts, now()),:dp,:rm,:pa,:by) RETURNING id"),
            {"o": principal.org_id, "b": branch, "c": data.customer_id, "g": data.godown_id, "no": number,
             "ob": data.orig_bill_id, "st": data.supply_type, "pm": data.price_mode, "rd": rdate,
             "dts": data.doc_datetime, "dp": data.discount_pct, "rm": data.remarks,
             "pa": data.payment_account_id, "by": principal.user_id},
        )
    ).scalar_one()

    out_lines = []
    for i, (line, m) in enumerate(zip(data.lines, computed.lines), start=1):
        godown_id = await doc_money.resolve_godown(session, branch, line.godown_id, data.godown_id)
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        hsn = line.hsn_code or await doc_money.product_hsn(session, line.product_id)
        cost = await eng.current_wac(session, principal.org_id, line.product_id, branch)
        # goods come BACK in
        await eng.move_stock(session, org_id=principal.org_id, branch_id=branch, godown_id=godown_id,
                             product_id=line.product_id, signed_qty=base, movement_type="return_in", cost=cost,
                             source=("sales_return", ret_id, i), effective_date=rdate, created_by=principal.user_id)
        await eng.apply_cost_inbound(session, principal.org_id, line.product_id, branch, base, cost)
        await session.execute(
            text("INSERT INTO sales_return_line (org_id, return_id, line_no, product_id, godown_id, entered_qty, "
                 "entered_unit_id, base_qty, rate, hsn_code, remarks, gross_amount, discount_pct, "
                 "discount_amount, header_discount_alloc, taxable, gst_rate, cgst, sgst, igst, line_total) "
                 "VALUES (:o,:r,:ln,:p,:g,:eq,:eu,:bq,:rt,:hsn,:rm,:gross,:dpct,:damt,:halloc,"
                 ":tx,:gr,:cg,:sg,:ig,:lt)"),
            {"o": principal.org_id, "r": ret_id, "ln": i, "p": line.product_id, "g": godown_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "bq": base, "rt": line.rate,
             "hsn": hsn, "rm": line.remarks, "gross": m.gross, "dpct": line.discount_pct or 0,
             "damt": m.discount, "halloc": m.header_discount_alloc, "tx": m.taxable,
             "gr": m.gst_rate, "cg": m.cgst, "sg": m.sgst, "ig": m.igst, "lt": m.line_total},
        )
        out_lines.append({
            "line_no": i, "product_id": line.product_id, "godown_id": godown_id,
            "entered_qty": line.entered_qty, "entered_unit_id": line.entered_unit_id,
            "base_qty": base, "rate": line.rate, "hsn_code": hsn, "remarks": line.remarks,
            "gross_amount": m.gross, "discount_amount": m.discount,
            "header_discount_alloc": m.header_discount_alloc, "taxable": m.taxable,
            "gst_rate": m.gst_rate, "cgst": m.cgst, "sgst": m.sgst, "igst": m.igst,
            "line_total": m.line_total,
        })

    await doc_money.write_totals(session, "sales_return", ret_id, t)
    # reduce customer receivable: CREDIT
    await post_party_entry(session, org_id=principal.org_id, branch_id=branch, party_id=data.customer_id,
                           entry_side="credit", amount=t.grand_total, source=("sales_return", ret_id, 0),
                           effective_date=rdate, created_by=principal.user_id)
    # cash refunded to the customer at the counter
    await doc_money.settle_at_post(
        session, org_id=principal.org_id, branch_id=branch, party_id=data.customer_id,
        account_id=data.payment_account_id, doc_type="sales_return", doc_id=ret_id,
        amount=t.paid_amount, effective_date=rdate, created_by=principal.user_id,
        party_side="debit", account_direction="out",
    )
    await emit(session, principal.org_id, "sale.return", {"return_id": ret_id, "customer_id": data.customer_id})
    return {"id": ret_id, "doc_no": number, "status": "posted", "customer_id": data.customer_id,
            "supply_type": data.supply_type, "price_mode": data.price_mode, "return_date": rdate,
            "lines": out_lines, "gross_total": t.gross_total,
            "line_discount_total": t.line_discount_total, "discount_amount": t.header_discount,
            "taxable_total": t.taxable_total, "tax_total": t.tax_total,
            "card_charges": t.card_charges, "round_off": t.round_off,
            "grand_total": t.grand_total, "paid_amount": t.paid_amount,
            "balance_amount": t.balance_amount}


# ---- amendment (v2 §7: editing a posted invoice) ----
async def cancel_bill(
    session: AsyncSession, principal: Principal, bill_id: int, reason: str | None = None
) -> dict:
    """Void a posted sales bill by reversing everything it did."""
    from app.services import reversal

    return await reversal.reverse_document(
        session, principal, "sales_bill", bill_id, reason=reason, action="cancel"
    )


async def amend_bill(
    session: AsyncSession, principal: Principal, bill_id: int, data: DirectBillCreate,
    reason: str | None = None,
) -> dict:
    """Replace a posted sales bill with a corrected revision.

    The original is reversed and marked cancelled, never edited — the ledgers
    are append-only and the stock has already moved. The two revisions point at
    each other so the original document number stays findable.
    """
    from app.services import reversal

    old = await reversal.load_document(session, "sales_bill", bill_id)
    reversal.assert_amendable(old, "sales_bill")

    await reversal.reverse_document(
        session, principal, "sales_bill", bill_id, reason=reason, action="amend"
    )
    # the correction keeps the original's customer and branch unless told otherwise
    payload = data.model_copy(update={
        "customer_id": data.customer_id or old["customer_id"],
        "branch_id": data.branch_id or old["branch_id"],
    })
    new = await post_direct_bill(session, principal, payload)
    await reversal.link_revision(
        session, "sales_bill", bill_id, new["id"], int(old["revision_no"]) + 1
    )
    await session.execute(
        text("UPDATE document_amendment SET replaced_by=:n WHERE doc_type='sales_bill' "
             "AND doc_id=:o AND action='amend' AND replaced_by IS NULL"),
        {"n": new["id"], "o": bill_id},
    )
    await emit(session, principal.org_id, "sale.bill.amended",
               {"old_bill_id": bill_id, "new_bill_id": new["id"], "reason": reason})
    return {**new, "amended_from": bill_id, "revision_no": int(old["revision_no"]) + 1}
