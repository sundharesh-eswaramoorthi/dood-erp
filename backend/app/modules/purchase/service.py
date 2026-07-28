"""Purchase bill posting — a thin caller of the Phase-2 engine primitives.

Goods-in: stock_engine.move_stock (+qty, movement_type 'purchase') and
apply_cost_inbound (moving-average). Money: party_ledger.post_entry as a CREDIT
to the supplier (we owe them). All in one request transaction.
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
from app.services import stock_engine as eng
from app.services.numbering import allocate
from app.services.outbox import emit
from app.services.party_ledger import post_entry as post_party_entry

Q2 = Decimal("0.01")


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
    number = await allocate(session, principal.org_id, None, "purchase_bill")
    bill_id = (
        await session.execute(
            text(
                "INSERT INTO purchase_bill (org_id, branch_id, supplier_id, godown_id, doc_no, "
                "supplier_invoice_no, supply_type, bill_date, created_by) "
                "VALUES (:o,:b,:s,:g,:no,:inv,:st,:bd,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "s": data.supplier_id, "g": data.godown_id,
             "no": number, "inv": data.supplier_invoice_no, "st": data.supply_type,
             "bd": bill_date, "by": principal.user_id},
        )
    ).scalar_one()

    taxable_total = Decimal(0)
    tax_total = Decimal(0)
    grand_total = Decimal(0)
    out_lines = []
    for i, line in enumerate(data.lines, start=1):
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        taxable = (Decimal(line.entered_qty) * Decimal(line.rate)).quantize(Q2)
        gst_rate = Decimal(line.gst_rate) if line.gst_rate is not None else await _product_gst(session, line.product_id)
        tax = (taxable * gst_rate / 100).quantize(Q2)
        if data.supply_type == "inter":
            cgst, sgst, igst = Decimal(0), Decimal(0), tax
        else:
            cgst = (tax / 2).quantize(Q2)
            sgst = (tax - cgst).quantize(Q2)  # keep cgst+sgst == tax exactly
            igst = Decimal(0)
        line_total = (taxable + tax).quantize(Q2)
        unit_cost = (taxable / base).quantize(Decimal("0.000001"))  # inventory cost ex-tax, per base unit

        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=branch_id, godown_id=data.godown_id,
            product_id=line.product_id, signed_qty=base, movement_type="purchase", cost=unit_cost,
            source=("purchase_bill", bill_id, i), effective_date=bill_date, created_by=principal.user_id,
        )
        await eng.apply_cost_inbound(session, principal.org_id, line.product_id, branch_id, base, unit_cost)

        await session.execute(
            text(
                "INSERT INTO purchase_bill_line (org_id, bill_id, line_no, product_id, entered_qty, "
                "entered_unit_id, base_qty, rate, taxable, gst_rate, cgst, sgst, igst, line_total) "
                "VALUES (:o,:bid,:ln,:p,:eq,:eu,:bq,:rt,:tx,:gr,:cg,:sg,:ig,:lt)"
            ),
            {"o": principal.org_id, "bid": bill_id, "ln": i, "p": line.product_id, "eq": line.entered_qty,
             "eu": line.entered_unit_id, "bq": base, "rt": line.rate, "tx": taxable, "gr": gst_rate,
             "cg": cgst, "sg": sgst, "ig": igst, "lt": line_total},
        )
        taxable_total += taxable
        tax_total += tax
        grand_total += line_total
        out_lines.append({"line_no": i, "product_id": line.product_id, "base_qty": base, "rate": line.rate,
                          "taxable": taxable, "gst_rate": gst_rate, "cgst": cgst, "sgst": sgst,
                          "igst": igst, "line_total": line_total})

    await session.execute(
        text("UPDATE purchase_bill SET taxable_total=:t, tax_total=:x, grand_total=:g WHERE id=:i"),
        {"t": taxable_total, "x": tax_total, "g": grand_total, "i": bill_id},
    )
    # supplier payable: CREDIT (we owe them)
    await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.supplier_id,
        entry_side="credit", amount=grand_total, source=("purchase_bill", bill_id, 0),
        effective_date=bill_date, created_by=principal.user_id,
    )
    await emit(session, principal.org_id, "purchase.bill",
               {"bill_id": bill_id, "supplier_id": data.supplier_id, "grand_total": str(grand_total)})
    return {"id": bill_id, "doc_no": number, "status": "posted", "supplier_id": data.supplier_id,
            "taxable_total": taxable_total, "tax_total": tax_total, "grand_total": grand_total, "lines": out_lines}


async def _product_gst(session: AsyncSession, product_id: int) -> Decimal:
    val = (
        await session.execute(text("SELECT gst_rate FROM product WHERE id=:p"), {"p": product_id})
    ).scalar_one_or_none()
    return Decimal(val) if val is not None else Decimal(0)


def _split_gst(taxable: Decimal, gst_rate: Decimal, supply_type: str):
    tax = (taxable * gst_rate / 100).quantize(Q2)
    if supply_type == "inter":
        return Decimal(0), Decimal(0), tax, tax
    cgst = (tax / 2).quantize(Q2)
    sgst = (tax - cgst).quantize(Q2)
    return cgst, sgst, Decimal(0), tax


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
    number = await allocate(session, principal.org_id, None, "purchase_return")
    ret_id = (
        await session.execute(
            text(
                "INSERT INTO purchase_return (org_id, branch_id, supplier_id, godown_id, doc_no, "
                "orig_bill_id, supply_type, return_date, created_by) "
                "VALUES (:o,:b,:s,:g,:no,:ob,:st,:rd,:by) RETURNING id"
            ),
            {"o": principal.org_id, "b": branch_id, "s": data.supplier_id, "g": data.godown_id,
             "no": number, "ob": data.orig_bill_id, "st": data.supply_type, "rd": rdate, "by": principal.user_id},
        )
    ).scalar_one()

    taxable_total = tax_total = grand_total = Decimal(0)
    out_lines = []
    for i, line in enumerate(data.lines, start=1):
        base = await eng.to_base(session, line.product_id, line.entered_qty, line.entered_unit_id)
        taxable = (Decimal(line.entered_qty) * Decimal(line.rate)).quantize(Q2)
        gst_rate = Decimal(line.gst_rate) if line.gst_rate is not None else await _product_gst(session, line.product_id)
        cgst, sgst, igst, tax = _split_gst(taxable, gst_rate, data.supply_type)
        line_total = (taxable + tax).quantize(Q2)
        cost = await eng.current_wac(session, principal.org_id, line.product_id, branch_id)
        allow_neg = await eng.product_allows_negative(session, line.product_id)

        # goods OUT (reverse of purchase)
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=branch_id, godown_id=data.godown_id,
            product_id=line.product_id, signed_qty=-base, movement_type="return_out", cost=cost,
            source=("purchase_return", ret_id, i), effective_date=rdate,
            created_by=principal.user_id, allow_negative=allow_neg,
        )
        await eng.apply_cost_outbound(session, principal.org_id, line.product_id, branch_id, base)

        await session.execute(
            text(
                "INSERT INTO purchase_return_line (org_id, return_id, line_no, product_id, entered_qty, "
                "entered_unit_id, base_qty, rate, taxable, gst_rate, cgst, sgst, igst, line_total) "
                "VALUES (:o,:r,:ln,:p,:eq,:eu,:bq,:rt,:tx,:gr,:cg,:sg,:ig,:lt)"
            ),
            {"o": principal.org_id, "r": ret_id, "ln": i, "p": line.product_id, "eq": line.entered_qty,
             "eu": line.entered_unit_id, "bq": base, "rt": line.rate, "tx": taxable, "gr": gst_rate,
             "cg": cgst, "sg": sgst, "ig": igst, "lt": line_total},
        )
        taxable_total += taxable
        tax_total += tax
        grand_total += line_total
        out_lines.append({"line_no": i, "product_id": line.product_id, "base_qty": base, "rate": line.rate,
                          "taxable": taxable, "gst_rate": gst_rate, "cgst": cgst, "sgst": sgst,
                          "igst": igst, "line_total": line_total})

    await session.execute(
        text("UPDATE purchase_return SET taxable_total=:t, tax_total=:x, grand_total=:g WHERE id=:i"),
        {"t": taxable_total, "x": tax_total, "g": grand_total, "i": ret_id},
    )
    # reduce supplier payable: DEBIT (they owe us the returned value back)
    await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.supplier_id,
        entry_side="debit", amount=grand_total, source=("purchase_return", ret_id, 0),
        effective_date=rdate, created_by=principal.user_id,
    )
    await emit(session, principal.org_id, "purchase.return",
               {"return_id": ret_id, "supplier_id": data.supplier_id, "grand_total": str(grand_total)})
    return {"id": ret_id, "doc_no": number, "status": "posted", "supplier_id": data.supplier_id,
            "taxable_total": taxable_total, "tax_total": tax_total, "grand_total": grand_total, "lines": out_lines}


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
