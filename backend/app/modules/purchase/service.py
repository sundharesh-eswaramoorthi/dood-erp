"""Purchase bill posting — a thin caller of the Phase-2 engine primitives.

Goods-in: stock_engine.move_stock (+qty, movement_type 'purchase') and
apply_cost_inbound (moving-average). Money: app.services.money computes the
v2 §3 block (line + overall discount, tax-inclusive entry, card charges, round
off) and party_ledger.post_entry credits the supplier. All in one transaction.

Each line carries its own godown, so one bill can receive into several
("multi godown invoice"). Inventory cost is the post-discount taxable per base
unit, so discounts land in the moving average rather than being lost.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.party import Party
from app.modules.purchase.schemas import (
    PurchaseBillCreate,
    PurchaseOrderCreate,
    PurchaseReturnCreate,
)
from app.services import doc_money, money
from app.services import stock_engine as eng
from app.services.numbering import allocate
from app.services.outbox import emit
from app.services.party_ledger import post_entry as post_party_entry

COST_Q = Decimal("0.000001")


async def _money_inputs(session: AsyncSession, lines) -> list[money.LineIn]:
    out = []
    for line in lines:
        gst = (
            Decimal(line.gst_rate)
            if line.gst_rate is not None
            else await _product_gst(session, line.product_id)
        )
        out.append(
            money.LineIn(
                qty=Decimal(line.entered_qty), rate=Decimal(line.rate), gst_rate=gst,
                discount_pct=Decimal(line.discount_pct or 0),
                discount_amount=line.discount_amount,
            )
        )
    return out


async def post_bill(session: AsyncSession, principal: Principal, data: PurchaseBillCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")

    supplier = (
        await session.execute(select(Party).where(Party.id == data.supplier_id))
    ).scalar_one_or_none()
    if supplier is None:
        raise ValueError("supplier not found")

    bill_date = data.bill_date or dt.date.today()
    computed = money.compute(
        await _money_inputs(session, data.lines),
        supply_type=data.supply_type, price_mode=data.price_mode,
        header_discount_pct=data.discount_pct, header_discount_amount=data.discount_amount,
        card_charges=data.card_charges, round_off=data.round_off, paid_amount=data.paid_amount,
    )
    t = computed.totals

    number = await allocate(session, principal.org_id, None, "purchase_bill")
    bill_id = (
        await session.execute(
            text(
                "INSERT INTO purchase_bill (org_id, branch_id, supplier_id, godown_id, doc_no, "
                "supplier_invoice_no, po_id, supply_type, price_mode, bill_date, doc_datetime, "
                "discount_pct, remarks, payment_account_id, created_by) "
                "VALUES (:o,:b,:s,:g,:no,:inv,:po,:st,:pm,:bd,COALESCE(:dts, now()),:dp,:rm,:pa,:by) "
                "RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "s": data.supplier_id, "g": data.godown_id,
             "no": number, "inv": data.supplier_invoice_no, "po": data.po_id, "st": data.supply_type,
             "pm": data.price_mode, "bd": bill_date, "dts": data.doc_datetime,
             "dp": data.discount_pct, "rm": data.remarks, "pa": data.payment_account_id,
             "by": principal.user_id},
        )
    ).scalar_one()

    out_lines = []
    for i, (line, m) in enumerate(zip(data.lines, computed.lines), start=1):
        godown_id = await doc_money.resolve_godown(session, branch_id, line.godown_id, data.godown_id)
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        hsn = line.hsn_code or await doc_money.product_hsn(session, line.product_id)
        # inventory cost is ex-tax and post-discount, per base unit
        unit_cost = (m.taxable / base).quantize(COST_Q)

        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=branch_id, godown_id=godown_id,
            product_id=line.product_id, signed_qty=base, movement_type="purchase", cost=unit_cost,
            source=("purchase_bill", bill_id, i), effective_date=bill_date, created_by=principal.user_id,
        )
        await eng.apply_cost_inbound(session, principal.org_id, line.product_id, branch_id, base, unit_cost)

        await session.execute(
            text(
                "INSERT INTO purchase_bill_line (org_id, bill_id, line_no, product_id, godown_id, "
                "entered_qty, entered_unit_id, base_qty, rate, hsn_code, remarks, gross_amount, "
                "discount_pct, discount_amount, header_discount_alloc, taxable, gst_rate, "
                "cgst, sgst, igst, line_total) "
                "VALUES (:o,:bid,:ln,:p,:g,:eq,:eu,:bq,:rt,:hsn,:rm,:gross,:dpct,:damt,:halloc,"
                ":tx,:gr,:cg,:sg,:ig,:lt)"
            ),
            {"o": principal.org_id, "bid": bill_id, "ln": i, "p": line.product_id, "g": godown_id,
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

    await doc_money.write_totals(session, "purchase_bill", bill_id, t)
    # supplier payable: CREDIT the full invoice (we owe them)
    await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.supplier_id,
        entry_side="credit", amount=t.grand_total, source=("purchase_bill", bill_id, 0),
        effective_date=bill_date, created_by=principal.user_id,
    )
    # anything paid on the spot settles straight back out of cash/bank
    await doc_money.settle_at_post(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.supplier_id,
        account_id=data.payment_account_id, doc_type="purchase_bill", doc_id=bill_id,
        amount=t.paid_amount, effective_date=bill_date, created_by=principal.user_id,
        party_side="debit", account_direction="out",
    )
    await emit(session, principal.org_id, "purchase.bill",
               {"bill_id": bill_id, "supplier_id": data.supplier_id, "grand_total": str(t.grand_total)})
    return {"id": bill_id, "doc_no": number, "status": "posted", "supplier_id": data.supplier_id,
            "supply_type": data.supply_type, "price_mode": data.price_mode, "bill_date": bill_date,
            "po_id": data.po_id, "lines": out_lines, **_totals_dict(t)}


def _totals_dict(t: money.Totals) -> dict:
    return {
        "gross_total": t.gross_total, "line_discount_total": t.line_discount_total,
        "discount_amount": t.header_discount, "taxable_total": t.taxable_total,
        "tax_total": t.tax_total, "card_charges": t.card_charges, "round_off": t.round_off,
        "grand_total": t.grand_total, "paid_amount": t.paid_amount,
        "balance_amount": t.balance_amount,
    }


async def _product_gst(session: AsyncSession, product_id: int) -> Decimal:
    val = (
        await session.execute(text("SELECT gst_rate FROM product WHERE id=:p"), {"p": product_id})
    ).scalar_one_or_none()
    return Decimal(val) if val is not None else Decimal(0)


async def post_return(session: AsyncSession, principal: Principal, data: PurchaseReturnCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    supplier = (await session.execute(select(Party).where(Party.id == data.supplier_id))).scalar_one_or_none()
    if supplier is None:
        raise ValueError("supplier not found")

    rdate = data.return_date or dt.date.today()
    computed = money.compute(
        await _money_inputs(session, data.lines),
        supply_type=data.supply_type, price_mode=data.price_mode,
        header_discount_pct=data.discount_pct, header_discount_amount=data.discount_amount,
        card_charges=data.card_charges, round_off=data.round_off, paid_amount=data.paid_amount,
    )
    t = computed.totals

    number = await allocate(session, principal.org_id, None, "purchase_return")
    ret_id = (
        await session.execute(
            text(
                "INSERT INTO purchase_return (org_id, branch_id, supplier_id, godown_id, doc_no, "
                "orig_bill_id, supply_type, price_mode, return_date, doc_datetime, discount_pct, "
                "remarks, payment_account_id, created_by) "
                "VALUES (:o,:b,:s,:g,:no,:ob,:st,:pm,:rd,COALESCE(:dts, now()),:dp,:rm,:pa,:by) "
                "RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "s": data.supplier_id, "g": data.godown_id,
             "no": number, "ob": data.orig_bill_id, "st": data.supply_type, "pm": data.price_mode,
             "rd": rdate, "dts": data.doc_datetime, "dp": data.discount_pct, "rm": data.remarks,
             "pa": data.payment_account_id, "by": principal.user_id},
        )
    ).scalar_one()

    out_lines = []
    for i, (line, m) in enumerate(zip(data.lines, computed.lines), start=1):
        godown_id = await doc_money.resolve_godown(session, branch_id, line.godown_id, data.godown_id)
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        hsn = line.hsn_code or await doc_money.product_hsn(session, line.product_id)
        cost = await eng.current_wac(session, principal.org_id, line.product_id, branch_id)
        allow_neg = await eng.product_allows_negative(session, line.product_id)

        # goods OUT (reverse of purchase)
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=branch_id, godown_id=godown_id,
            product_id=line.product_id, signed_qty=-base, movement_type="return_out", cost=cost,
            source=("purchase_return", ret_id, i), effective_date=rdate,
            created_by=principal.user_id, allow_negative=allow_neg,
        )
        await eng.apply_cost_outbound(session, principal.org_id, line.product_id, branch_id, base)

        await session.execute(
            text(
                "INSERT INTO purchase_return_line (org_id, return_id, line_no, product_id, godown_id, "
                "entered_qty, entered_unit_id, base_qty, rate, hsn_code, remarks, gross_amount, "
                "discount_pct, discount_amount, header_discount_alloc, taxable, gst_rate, "
                "cgst, sgst, igst, line_total) "
                "VALUES (:o,:r,:ln,:p,:g,:eq,:eu,:bq,:rt,:hsn,:rm,:gross,:dpct,:damt,:halloc,"
                ":tx,:gr,:cg,:sg,:ig,:lt)"
            ),
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

    await doc_money.write_totals(session, "purchase_return", ret_id, t)
    # reduce supplier payable: DEBIT (they owe us the returned value back)
    await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.supplier_id,
        entry_side="debit", amount=t.grand_total, source=("purchase_return", ret_id, 0),
        effective_date=rdate, created_by=principal.user_id,
    )
    # a refund taken in cash at return time: money comes back IN to us
    await doc_money.settle_at_post(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.supplier_id,
        account_id=data.payment_account_id, doc_type="purchase_return", doc_id=ret_id,
        amount=t.paid_amount, effective_date=rdate, created_by=principal.user_id,
        party_side="credit", account_direction="in",
    )
    await emit(session, principal.org_id, "purchase.return",
               {"return_id": ret_id, "supplier_id": data.supplier_id, "grand_total": str(t.grand_total)})
    return {"id": ret_id, "doc_no": number, "status": "posted", "supplier_id": data.supplier_id,
            "supply_type": data.supply_type, "price_mode": data.price_mode, "return_date": rdate,
            "lines": out_lines, **_totals_dict(t)}


async def feature_enabled(session: AsyncSession, org_id: int, key: str) -> bool:
    val = (
        await session.execute(
            text("SELECT value->>'enabled' FROM system_setting WHERE org_id=:o AND key=:k"),
            {"o": org_id, "k": f"feature.{key}"},
        )
    ).scalar_one_or_none()
    return val == "true"


async def create_po(session: AsyncSession, principal: Principal, data: PurchaseOrderCreate) -> dict:
    if not await feature_enabled(session, principal.org_id, "purchase_order"):
        raise PermissionError("Purchase Order feature is disabled in Settings")
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None or branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    number = await allocate(session, principal.org_id, None, "purchase_order")
    po_id = (
        await session.execute(
            text(
                "INSERT INTO purchase_order (org_id, branch_id, supplier_id, doc_no, order_date, "
                "expected_date, note, created_by) VALUES (:o,:b,:s,:no,:od,:ed,:nt,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "s": data.supplier_id, "no": number,
             "od": data.order_date or dt.date.today(), "ed": data.expected_date, "nt": data.note,
             "by": principal.user_id},
        )
    ).scalar_one()
    for i, line in enumerate(data.lines, start=1):
        await session.execute(
            text(
                "INSERT INTO purchase_order_line (org_id, po_id, line_no, product_id, entered_qty, "
                "entered_unit_id, rate) VALUES (:o,:po,:ln,:p,:eq,:eu,:rt)"
            ),
            {"o": principal.org_id, "po": po_id, "ln": i, "p": line.product_id,
             "eq": line.entered_qty, "eu": line.entered_unit_id, "rt": line.rate},
        )
    return {"id": po_id, "doc_no": number, "status": "open", "supplier_id": data.supplier_id}


async def list_po(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, doc_no, supplier_id, order_date, status FROM purchase_order ORDER BY id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_bills(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, doc_no, supplier_id, bill_date, grand_total, status "
                "FROM purchase_bill ORDER BY id DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
