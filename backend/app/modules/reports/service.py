"""v2 §6 — the full report set (48 across 8 groups), replacing the 7 flat ones.

Every report returns {"summary": {...}, "rows": [...]} and is registered in
REPORTS with its group and title, so the API can serve a catalogue and the UI
can build its picker from data rather than a hard-coded list.

Two things that apply across the board:

* Cancelled documents are excluded everywhere. V2.8 made invoices amendable by
  reversing the original and posting a revision, so a cancelled bill and its
  replacement both exist. Counting both would double every amended invoice.
* Money leaves as decimal strings. These figures get printed and reconciled;
  a float would show 1050 where the document says 1050.00.

Figures come from the same ledgers the documents posted to, so a report and the
party/stock balance it describes cannot disagree.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal

POSTED = "status = 'posted'"


@dataclass
class Filters:
    """Everything a report may narrow by; each report uses what applies."""

    date_from: dt.date
    date_to: dt.date
    branch_id: int | None = None
    party_id: int | None = None
    product_id: int | None = None
    category_id: int | None = None
    godown_id: int | None = None
    payment_type_id: int | None = None

    def params(self) -> dict:
        return {
            "f": self.date_from, "t": self.date_to, "branch": self.branch_id,
            "party": self.party_id, "product": self.product_id,
            "category": self.category_id, "godown": self.godown_id,
            "ptype": self.payment_type_id,
        }


def _opt(clause: str, value) -> str:
    """Include a WHERE fragment only when its parameter was supplied."""
    return f" AND {clause}" if value is not None else ""


def _clean(value):
    return str(value) if isinstance(value, Decimal) else value


async def _rows(session: AsyncSession, sql: str, p: dict) -> list[dict]:
    res = (await session.execute(text(sql), p)).mappings().all()
    return [{k: _clean(v) for k, v in r.items()} for r in res]


async def _one(session: AsyncSession, sql: str, p: dict) -> dict:
    res = (await session.execute(text(sql), p)).mappings().one()
    return {k: _clean(v) for k, v in res.items()}


# =====================================================================
# SALES (v2 §6 — 10 reports)
# =====================================================================
def _sales_where(f: Filters) -> str:
    return (
        f"sb.bill_date BETWEEN :f AND :t AND sb.{POSTED}"
        + _opt("sb.branch_id = :branch", f.branch_id)
        + _opt("sb.customer_id = :party", f.party_id)
        + _opt("sb.payment_type_id = :ptype", f.payment_type_id)
    )


async def _sales_summary_row(session, f: Filters) -> dict:
    return await _one(session,
        f"SELECT COUNT(*) AS bills, COALESCE(SUM(sb.gross_total),0) AS gross, "
        f"COALESCE(SUM(sb.line_discount_total + sb.discount_amount),0) AS discount, "
        f"COALESCE(SUM(sb.taxable_total),0) AS taxable, COALESCE(SUM(sb.tax_total),0) AS tax, "
        f"COALESCE(SUM(sb.grand_total),0) AS total, COALESCE(SUM(sb.paid_amount),0) AS paid, "
        f"COALESCE(SUM(sb.balance_amount),0) AS balance "
        f"FROM sales_bill sb WHERE {_sales_where(f)}", f.params())


async def sales_summary(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT sb.bill_date AS date, COUNT(*) AS bills, "
        f"SUM(sb.taxable_total) AS taxable, SUM(sb.tax_total) AS tax, "
        f"SUM(sb.grand_total) AS total "
        f"FROM sales_bill sb WHERE {_sales_where(f)} "
        f"GROUP BY sb.bill_date ORDER BY sb.bill_date", f.params())
    return {"summary": await _sales_summary_row(session, f), "rows": rows}


async def sales_detailed(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT sb.doc_no, sb.bill_date AS date, pt.name AS party, br.name AS branch, "
        f"sb.supply_type, sb.gross_total, sb.line_discount_total + sb.discount_amount AS discount, "
        f"sb.taxable_total, sb.tax_total, sb.round_off, sb.grand_total, sb.paid_amount, "
        f"sb.balance_amount, ptp.name AS payment_type "
        f"FROM sales_bill sb LEFT JOIN party pt ON pt.id = sb.customer_id "
        f"LEFT JOIN branch br ON br.id = sb.branch_id "
        f"LEFT JOIN payment_type ptp ON ptp.id = sb.payment_type_id "
        f"WHERE {_sales_where(f)} ORDER BY sb.bill_date, sb.id", f.params())
    return {"summary": await _sales_summary_row(session, f), "rows": rows}


async def _sales_grouped(session, f: Filters, select: str, join: str, group: str) -> dict:
    rows = await _rows(session,
        f"SELECT {select}, SUM(sbl.base_qty) AS qty, SUM(sbl.taxable) AS taxable, "
        f"SUM(sbl.cgst + sbl.sgst + sbl.igst) AS tax, SUM(sbl.line_total) AS total, "
        f"SUM(sbl.cogs_amount) AS cogs, SUM(sbl.taxable - sbl.cogs_amount) AS gross_profit "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id {join} "
        f"WHERE {_sales_where(f)}"
        + _opt("sbl.product_id = :product", f.product_id)
        + _opt("pr.category_id = :category", f.category_id)
        + f" GROUP BY {group} ORDER BY total DESC NULLS LAST", f.params())
    return {"summary": await _sales_summary_row(session, f), "rows": rows}


async def sales_by_product(session, principal, f: Filters) -> dict:
    return await _sales_grouped(session, f, "pr.code, pr.name AS product",
                                "JOIN product pr ON pr.id = sbl.product_id", "pr.code, pr.name")


async def sales_by_party(session, principal, f: Filters) -> dict:
    return await _sales_grouped(session, f, "pt.party_code, pt.name AS party, pt.area",
                                "JOIN product pr ON pr.id = sbl.product_id "
                                "LEFT JOIN party pt ON pt.id = sb.customer_id",
                                "pt.party_code, pt.name, pt.area")


async def sales_by_category(session, principal, f: Filters) -> dict:
    return await _sales_grouped(session, f, "COALESCE(c.name,'Uncategorised') AS category",
                                "JOIN product pr ON pr.id = sbl.product_id "
                                "LEFT JOIN product_category c ON c.id = pr.category_id", "c.name")


async def sales_by_branch(session, principal, f: Filters) -> dict:
    return await _sales_grouped(session, f, "br.name AS branch",
                                "JOIN product pr ON pr.id = sbl.product_id "
                                "LEFT JOIN branch br ON br.id = sb.branch_id", "br.name")


async def sales_by_payment_mode(session, principal, f: Filters) -> dict:
    """v2 §6 "Payment Mode-wise Sales" — reads the payment_type master added in
    V2.7. Bills with no type recorded group under 'Unspecified'."""
    rows = await _rows(session,
        f"SELECT COALESCE(pt.name,'Unspecified') AS payment_type, COUNT(*) AS bills, "
        f"SUM(sb.grand_total) AS total, SUM(sb.paid_amount) AS paid, "
        f"SUM(sb.balance_amount) AS balance "
        f"FROM sales_bill sb LEFT JOIN payment_type pt ON pt.id = sb.payment_type_id "
        f"WHERE {_sales_where(f)} GROUP BY pt.name ORDER BY total DESC", f.params())
    return {"summary": await _sales_summary_row(session, f), "rows": rows}


async def sales_gst(session, principal, f: Filters) -> dict:
    """GSTR-1 shaped: taxable and tax by rate and supply type."""
    rows = await _rows(session,
        f"SELECT sbl.gst_rate, sb.supply_type, COALESCE(sbl.hsn_code,'-') AS hsn, "
        f"SUM(sbl.taxable) AS taxable, SUM(sbl.cgst) AS cgst, SUM(sbl.sgst) AS sgst, "
        f"SUM(sbl.igst) AS igst, SUM(sbl.cgst + sbl.sgst + sbl.igst) AS tax "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id "
        f"WHERE {_sales_where(f)} "
        f"GROUP BY sbl.gst_rate, sb.supply_type, sbl.hsn_code "
        f"ORDER BY sbl.gst_rate, sb.supply_type", f.params())
    summary = await _one(session,
        f"SELECT COALESCE(SUM(sbl.taxable),0) AS taxable, COALESCE(SUM(sbl.cgst),0) AS cgst, "
        f"COALESCE(SUM(sbl.sgst),0) AS sgst, COALESCE(SUM(sbl.igst),0) AS igst, "
        f"COALESCE(SUM(sbl.cgst + sbl.sgst + sbl.igst),0) AS tax "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id "
        f"WHERE {_sales_where(f)}", f.params())
    return {"summary": summary, "rows": rows}


async def sales_returns(session, principal, f: Filters) -> dict:
    where = (f"sr.return_date BETWEEN :f AND :t AND sr.{POSTED}"
             + _opt("sr.branch_id = :branch", f.branch_id)
             + _opt("sr.customer_id = :party", f.party_id))
    rows = await _rows(session,
        f"SELECT sr.doc_no, sr.return_date AS date, pt.name AS party, sr.orig_bill_id, "
        f"sr.taxable_total, sr.tax_total, sr.grand_total "
        f"FROM sales_return sr LEFT JOIN party pt ON pt.id = sr.customer_id "
        f"WHERE {where} ORDER BY sr.return_date, sr.id", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS returns, COALESCE(SUM(sr.taxable_total),0) AS taxable, "
        f"COALESCE(SUM(sr.tax_total),0) AS tax, COALESCE(SUM(sr.grand_total),0) AS total "
        f"FROM sales_return sr WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def sales_orders(session, principal, f: Filters) -> dict:
    where = ("so.order_date BETWEEN :f AND :t"
             + _opt("so.branch_id = :branch", f.branch_id)
             + _opt("so.customer_id = :party", f.party_id))
    rows = await _rows(session,
        f"SELECT so.doc_no, so.order_date AS date, pt.name AS party, so.status, "
        f"so.grand_total, "
        f"(SELECT COALESCE(SUM(sol.base_qty),0) FROM sale_order_line sol WHERE sol.order_id = so.id) AS ordered_qty, "
        f"(SELECT COALESCE(SUM(sf.moved_qty),0) FROM stock_fulfillment sf WHERE sf.sale_order_id = so.id) AS delivered_qty "
        f"FROM sale_order so LEFT JOIN party pt ON pt.id = so.customer_id "
        f"WHERE {where} ORDER BY so.order_date, so.id", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS orders, COALESCE(SUM(so.grand_total),0) AS total, "
        f"COUNT(*) FILTER (WHERE so.status = 'pending') AS pending, "
        f"COUNT(*) FILTER (WHERE so.status = 'delivered') AS delivered, "
        f"COUNT(*) FILTER (WHERE so.status = 'cancelled') AS cancelled "
        f"FROM sale_order so WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


# =====================================================================
# PURCHASE (v2 §6 — 9 reports)
# =====================================================================
def _purchase_where(f: Filters) -> str:
    return (
        f"pb.bill_date BETWEEN :f AND :t AND pb.{POSTED}"
        + _opt("pb.branch_id = :branch", f.branch_id)
        + _opt("pb.supplier_id = :party", f.party_id)
    )


async def _purchase_summary_row(session, f: Filters) -> dict:
    return await _one(session,
        f"SELECT COUNT(*) AS bills, COALESCE(SUM(pb.gross_total),0) AS gross, "
        f"COALESCE(SUM(pb.line_discount_total + pb.discount_amount),0) AS discount, "
        f"COALESCE(SUM(pb.taxable_total),0) AS taxable, COALESCE(SUM(pb.tax_total),0) AS tax, "
        f"COALESCE(SUM(pb.grand_total),0) AS total, COALESCE(SUM(pb.paid_amount),0) AS paid, "
        f"COALESCE(SUM(pb.balance_amount),0) AS balance "
        f"FROM purchase_bill pb WHERE {_purchase_where(f)}", f.params())


async def purchase_summary(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT pb.bill_date AS date, COUNT(*) AS bills, SUM(pb.taxable_total) AS taxable, "
        f"SUM(pb.tax_total) AS tax, SUM(pb.grand_total) AS total "
        f"FROM purchase_bill pb WHERE {_purchase_where(f)} "
        f"GROUP BY pb.bill_date ORDER BY pb.bill_date", f.params())
    return {"summary": await _purchase_summary_row(session, f), "rows": rows}


async def purchase_detailed(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT pb.doc_no, pb.bill_date AS date, pb.supplier_invoice_no, pt.name AS party, "
        f"br.name AS branch, pb.supply_type, pb.gross_total, "
        f"pb.line_discount_total + pb.discount_amount AS discount, pb.taxable_total, "
        f"pb.tax_total, pb.round_off, pb.grand_total, pb.paid_amount, pb.balance_amount, "
        f"pb.po_id "
        f"FROM purchase_bill pb LEFT JOIN party pt ON pt.id = pb.supplier_id "
        f"LEFT JOIN branch br ON br.id = pb.branch_id "
        f"WHERE {_purchase_where(f)} ORDER BY pb.bill_date, pb.id", f.params())
    return {"summary": await _purchase_summary_row(session, f), "rows": rows}


async def _purchase_grouped(session, f: Filters, select: str, join: str, group: str) -> dict:
    rows = await _rows(session,
        f"SELECT {select}, SUM(pbl.base_qty) AS qty, SUM(pbl.taxable) AS taxable, "
        f"SUM(pbl.cgst + pbl.sgst + pbl.igst) AS tax, SUM(pbl.line_total) AS total "
        f"FROM purchase_bill_line pbl JOIN purchase_bill pb ON pb.id = pbl.bill_id {join} "
        f"WHERE {_purchase_where(f)}"
        + _opt("pbl.product_id = :product", f.product_id)
        + _opt("pr.category_id = :category", f.category_id)
        + f" GROUP BY {group} ORDER BY total DESC NULLS LAST", f.params())
    return {"summary": await _purchase_summary_row(session, f), "rows": rows}


async def purchase_by_product(session, principal, f: Filters) -> dict:
    return await _purchase_grouped(session, f, "pr.code, pr.name AS product",
                                   "JOIN product pr ON pr.id = pbl.product_id", "pr.code, pr.name")


async def purchase_by_party(session, principal, f: Filters) -> dict:
    return await _purchase_grouped(session, f, "pt.party_code, pt.name AS party",
                                   "JOIN product pr ON pr.id = pbl.product_id "
                                   "LEFT JOIN party pt ON pt.id = pb.supplier_id",
                                   "pt.party_code, pt.name")


async def purchase_by_category(session, principal, f: Filters) -> dict:
    return await _purchase_grouped(session, f, "COALESCE(c.name,'Uncategorised') AS category",
                                   "JOIN product pr ON pr.id = pbl.product_id "
                                   "LEFT JOIN product_category c ON c.id = pr.category_id", "c.name")


async def purchase_by_branch(session, principal, f: Filters) -> dict:
    return await _purchase_grouped(session, f, "br.name AS branch",
                                   "JOIN product pr ON pr.id = pbl.product_id "
                                   "LEFT JOIN branch br ON br.id = pb.branch_id", "br.name")


async def purchase_gst(session, principal, f: Filters) -> dict:
    """Input tax credit, by rate and supply type."""
    rows = await _rows(session,
        f"SELECT pbl.gst_rate, pb.supply_type, COALESCE(pbl.hsn_code,'-') AS hsn, "
        f"SUM(pbl.taxable) AS taxable, SUM(pbl.cgst) AS cgst, SUM(pbl.sgst) AS sgst, "
        f"SUM(pbl.igst) AS igst, SUM(pbl.cgst + pbl.sgst + pbl.igst) AS tax "
        f"FROM purchase_bill_line pbl JOIN purchase_bill pb ON pb.id = pbl.bill_id "
        f"WHERE {_purchase_where(f)} "
        f"GROUP BY pbl.gst_rate, pb.supply_type, pbl.hsn_code "
        f"ORDER BY pbl.gst_rate, pb.supply_type", f.params())
    summary = await _one(session,
        f"SELECT COALESCE(SUM(pbl.taxable),0) AS taxable, COALESCE(SUM(pbl.cgst),0) AS cgst, "
        f"COALESCE(SUM(pbl.sgst),0) AS sgst, COALESCE(SUM(pbl.igst),0) AS igst, "
        f"COALESCE(SUM(pbl.cgst + pbl.sgst + pbl.igst),0) AS input_tax_credit "
        f"FROM purchase_bill_line pbl JOIN purchase_bill pb ON pb.id = pbl.bill_id "
        f"WHERE {_purchase_where(f)}", f.params())
    return {"summary": summary, "rows": rows}


async def purchase_returns(session, principal, f: Filters) -> dict:
    where = (f"pr2.return_date BETWEEN :f AND :t AND pr2.{POSTED}"
             + _opt("pr2.branch_id = :branch", f.branch_id)
             + _opt("pr2.supplier_id = :party", f.party_id))
    rows = await _rows(session,
        f"SELECT pr2.doc_no, pr2.return_date AS date, pt.name AS party, pr2.orig_bill_id, "
        f"pr2.taxable_total, pr2.tax_total, pr2.grand_total "
        f"FROM purchase_return pr2 LEFT JOIN party pt ON pt.id = pr2.supplier_id "
        f"WHERE {where} ORDER BY pr2.return_date, pr2.id", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS returns, COALESCE(SUM(pr2.taxable_total),0) AS taxable, "
        f"COALESCE(SUM(pr2.tax_total),0) AS tax, COALESCE(SUM(pr2.grand_total),0) AS total "
        f"FROM purchase_return pr2 WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def purchase_orders(session, principal, f: Filters) -> dict:
    where = ("po.order_date BETWEEN :f AND :t"
             + _opt("po.branch_id = :branch", f.branch_id)
             + _opt("po.supplier_id = :party", f.party_id))
    rows = await _rows(session,
        f"SELECT po.doc_no, po.order_date AS date, po.expected_date, pt.name AS party, "
        f"po.status, po.grand_total, po.advance_amount, po.balance_amount, "
        f"(SELECT COALESCE(SUM(pol.base_qty),0) FROM purchase_order_line pol WHERE pol.po_id = po.id) AS ordered_qty, "
        f"(SELECT COALESCE(SUM(pol.received_qty),0) FROM purchase_order_line pol WHERE pol.po_id = po.id) AS received_qty "
        f"FROM purchase_order po LEFT JOIN party pt ON pt.id = po.supplier_id "
        f"WHERE {where} ORDER BY po.order_date, po.id", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS orders, COALESCE(SUM(po.grand_total),0) AS total, "
        f"COALESCE(SUM(po.advance_amount),0) AS advance, "
        f"COUNT(*) FILTER (WHERE po.status IN ('open','approved')) AS open, "
        f"COUNT(*) FILTER (WHERE po.status = 'partial') AS partial, "
        f"COUNT(*) FILTER (WHERE po.status = 'closed') AS closed "
        f"FROM purchase_order po WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


# =====================================================================
# STOCK (v2 §6 — 11 reports)
# =====================================================================
_STOCK_BASE = (
    "FROM stock_balance b "
    "JOIN product p ON p.id = b.product_id "
    "LEFT JOIN product_category c ON c.id = p.category_id "
    "LEFT JOIN branch br ON br.id = b.branch_id "
    "LEFT JOIN godown g ON g.id = b.godown_id "
    "LEFT JOIN product_cost pc ON pc.org_id = b.org_id AND pc.product_id = b.product_id "
    "     AND pc.branch_id = b.branch_id "
    "WHERE b.location_state = 'on_hand'"
)


def _stock_where(f: Filters) -> str:
    return (_STOCK_BASE
            + _opt("b.branch_id = :branch", f.branch_id)
            + _opt("b.godown_id = :godown", f.godown_id)
            + _opt("b.product_id = :product", f.product_id)
            + _opt("p.category_id = :category", f.category_id))


async def _stock_totals(session, f: Filters) -> dict:
    return await _one(session,
        "SELECT COUNT(DISTINCT b.product_id) AS products, COALESCE(SUM(b.on_hand),0) AS qty, "
        "COALESCE(SUM(b.on_hand * COALESCE(pc.moving_avg_cost,0)),0) AS value "
        + _stock_where(f), f.params())


async def _stock_grouped(session, f: Filters, select: str, group: str, having: str = "") -> dict:
    rows = await _rows(session,
        f"SELECT {select}, SUM(b.on_hand) AS qty, SUM(b.reserved) AS reserved, "
        f"SUM(b.on_hand - b.reserved) AS available, "
        f"MAX(COALESCE(pc.moving_avg_cost,0)) AS avg_cost, "
        f"SUM(b.on_hand * COALESCE(pc.moving_avg_cost,0)) AS value "
        + _stock_where(f) + f" GROUP BY {group} {having} ORDER BY value DESC NULLS LAST",
        f.params())
    return {"summary": await _stock_totals(session, f), "rows": rows}


async def stock_current(session, principal, f: Filters) -> dict:
    return await _stock_grouped(session, f, "p.code, p.name AS product, br.name AS branch, g.name AS godown",
                                "p.code, p.name, br.name, g.name")


async def stock_by_branch(session, principal, f: Filters) -> dict:
    return await _stock_grouped(session, f, "br.name AS branch", "br.name")


async def stock_by_godown(session, principal, f: Filters) -> dict:
    return await _stock_grouped(session, f, "br.name AS branch, g.name AS godown", "br.name, g.name")


async def stock_by_product(session, principal, f: Filters) -> dict:
    return await _stock_grouped(session, f, "p.code, p.name AS product", "p.code, p.name")


async def stock_by_category(session, principal, f: Filters) -> dict:
    return await _stock_grouped(session, f, "COALESCE(c.name,'Uncategorised') AS category", "c.name")


async def stock_value(session, principal, f: Filters) -> dict:
    """Valuation at the moving average, which is what the COGS on every sales
    line was taken from."""
    return await _stock_grouped(session, f, "p.code, p.name AS product", "p.code, p.name")


async def stock_low(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        "SELECT p.code, p.name AS product, br.name AS branch, "
        "       COALESCE(SUM(b.on_hand),0) AS qty, MIN(rt.min_qty) AS min_qty, "
        "       MIN(rt.min_qty) - COALESCE(SUM(b.on_hand),0) AS shortfall "
        "FROM reorder_threshold rt JOIN product p ON p.id = rt.product_id "
        "LEFT JOIN branch br ON br.id = rt.branch_id "
        "LEFT JOIN stock_balance b ON b.product_id = rt.product_id "
        "     AND b.branch_id = rt.branch_id AND b.location_state = 'on_hand' "
        "WHERE TRUE"
        + _opt("rt.branch_id = :branch", f.branch_id)
        + _opt("p.category_id = :category", f.category_id)
        + " GROUP BY p.code, p.name, br.name, rt.product_id "
        "HAVING COALESCE(SUM(b.on_hand),0) < MIN(rt.min_qty) "
        "ORDER BY shortfall DESC", f.params())
    return {"summary": {"below_reorder_level": len(rows)}, "rows": rows}


async def stock_zero(session, principal, f: Filters) -> dict:
    """Products carrying no stock — the ones that cannot be sold today."""
    rows = await _rows(session,
        "SELECT p.code, p.name AS product, COALESCE(c.name,'Uncategorised') AS category, "
        "       COALESCE(SUM(b.on_hand),0) AS qty "
        "FROM product p LEFT JOIN product_category c ON c.id = p.category_id "
        "LEFT JOIN stock_balance b ON b.product_id = p.id AND b.location_state = 'on_hand' "
        "WHERE p.is_active"
        + _opt("p.category_id = :category", f.category_id)
        + " GROUP BY p.code, p.name, c.name "
        "HAVING COALESCE(SUM(b.on_hand),0) <= 0 ORDER BY p.name", f.params())
    return {"summary": {"products_out_of_stock": len(rows)}, "rows": rows}


async def stock_movement(session, principal, f: Filters) -> dict:
    where = ("l.effective_date BETWEEN :f AND :t AND l.entry_purpose = 'original'"
             + _opt("l.branch_id = :branch", f.branch_id)
             + _opt("l.godown_id = :godown", f.godown_id)
             + _opt("l.product_id = :product", f.product_id)
             + _opt("p.category_id = :category", f.category_id))
    rows = await _rows(session,
        f"SELECT l.effective_date AS date, p.code, p.name AS product, g.name AS godown, "
        f"l.movement_type, l.signed_qty AS qty, l.unit_cost, l.source_doc_type, l.source_doc_id "
        f"FROM stock_movement_ledger l JOIN product p ON p.id = l.product_id "
        f"LEFT JOIN godown g ON g.id = l.godown_id "
        f"WHERE {where} ORDER BY l.effective_date, l.id", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS movements, "
        f"COALESCE(SUM(l.signed_qty) FILTER (WHERE l.signed_qty > 0),0) AS qty_in, "
        f"COALESCE(-SUM(l.signed_qty) FILTER (WHERE l.signed_qty < 0),0) AS qty_out, "
        f"COALESCE(SUM(l.signed_qty),0) AS net "
        f"FROM stock_movement_ledger l JOIN product p ON p.id = l.product_id "
        f"WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def stock_adjustments(session, principal, f: Filters) -> dict:
    where = ("a.effective_date BETWEEN :f AND :t"
             + _opt("a.branch_id = :branch", f.branch_id)
             + _opt("a.godown_id = :godown", f.godown_id)
             + _opt("al.product_id = :product", f.product_id))
    rows = await _rows(session,
        f"SELECT a.doc_no, a.effective_date AS date, a.adj_reason, g.name AS godown, "
        f"p.code, p.name AS product, al.base_qty AS qty, al.unit_cost, a.note "
        f"FROM stock_adjustment a JOIN stock_adjustment_line al ON al.adjustment_id = a.id "
        f"JOIN product p ON p.id = al.product_id LEFT JOIN godown g ON g.id = a.godown_id "
        f"WHERE {where} ORDER BY a.effective_date, a.id, al.line_no", f.params())
    summary = await _one(session,
        f"SELECT COUNT(DISTINCT a.id) AS adjustments, COALESCE(SUM(al.base_qty),0) AS qty "
        f"FROM stock_adjustment a JOIN stock_adjustment_line al ON al.adjustment_id = a.id "
        f"WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def stock_verifications(session, principal, f: Filters) -> dict:
    where = ("v.started_at::date BETWEEN :f AND :t"
             + _opt("v.branch_id = :branch", f.branch_id)
             + _opt("v.godown_id = :godown", f.godown_id))
    rows = await _rows(session,
        f"SELECT v.doc_no, v.started_at::date AS date, v.status, g.name AS godown, "
        f"p.code, p.name AS product, vl.system_qty_at_start AS system_qty, "
        f"vl.physical_qty, vl.physical_qty - vl.system_qty_at_start AS difference "
        f"FROM stock_verification v JOIN stock_verification_line vl ON vl.verification_id = v.id "
        f"JOIN product p ON p.id = vl.product_id LEFT JOIN godown g ON g.id = v.godown_id "
        f"WHERE {where} ORDER BY v.started_at, v.id, vl.line_no", f.params())
    summary = await _one(session,
        f"SELECT COUNT(DISTINCT v.id) AS verifications, "
        f"COALESCE(SUM(vl.physical_qty - vl.system_qty_at_start),0) AS net_difference "
        f"FROM stock_verification v JOIN stock_verification_line vl ON vl.verification_id = v.id "
        f"WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


# =====================================================================
# PARTY (v2 §6 — 5 reports)
# =====================================================================
async def party_ledger(session, principal, f: Filters) -> dict:
    where = ("e.effective_date BETWEEN :f AND :t"
             + _opt("e.party_id = :party", f.party_id)
             + _opt("e.branch_id = :branch", f.branch_id))
    rows = await _rows(session,
        f"SELECT e.effective_date AS date, pt.name AS party, e.source_doc_type, "
        f"e.source_doc_id, e.entry_purpose, "
        f"CASE WHEN e.entry_side='debit' THEN e.amount END AS debit, "
        f"CASE WHEN e.entry_side='credit' THEN e.amount END AS credit "
        f"FROM party_ledger_entry e LEFT JOIN party pt ON pt.id = e.party_id "
        f"WHERE {where} ORDER BY e.effective_date, e.id", f.params())
    summary = await _one(session,
        f"SELECT COALESCE(SUM(e.amount) FILTER (WHERE e.entry_side='debit'),0) AS debit, "
        f"COALESCE(SUM(e.amount) FILTER (WHERE e.entry_side='credit'),0) AS credit, "
        f"COALESCE(SUM(CASE WHEN e.entry_side='debit' THEN e.amount ELSE -e.amount END),0) AS net "
        f"FROM party_ledger_entry e WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def party_outstanding(session, principal, f: Filters) -> dict:
    """Bill-wise outstanding with ageing — reads the allocations wired in V2.7,
    so it says which bills are open rather than just a party total."""
    where = ("e.entry_purpose = 'original' AND e.source_doc_type NOT LIKE '%_payment' "
             "AND e.source_doc_type <> 'payment_voucher' "
             "AND NOT EXISTS (SELECT 1 FROM party_ledger_entry r "
             "  WHERE r.org_id = e.org_id AND r.source_doc_type = e.source_doc_type "
             "    AND r.source_doc_id = e.source_doc_id AND r.source_line_no = e.source_line_no "
             "    AND r.entry_purpose = 'reversal' AND r.reversal_seq > e.reversal_seq)"
             + _opt("e.party_id = :party", f.party_id)
             + _opt("e.branch_id = :branch", f.branch_id))
    rows = await _rows(session,
        f"SELECT pt.party_code, pt.name AS party, pt.area, e.entry_side, "
        f"e.source_doc_type, e.source_doc_id, e.effective_date AS date, e.amount, "
        f"COALESCE(a.settled,0) AS settled, e.amount - COALESCE(a.settled,0) AS outstanding, "
        f"(CURRENT_DATE - e.effective_date) AS age_days "
        f"FROM party_ledger_entry e LEFT JOIN party pt ON pt.id = e.party_id "
        f"LEFT JOIN (SELECT against_entry_id, SUM(amount) AS settled FROM ledger_allocation "
        f"           GROUP BY against_entry_id) a ON a.against_entry_id = e.id "
        f"WHERE {where} AND e.amount - COALESCE(a.settled,0) > 0 "
        f"ORDER BY age_days DESC, pt.name", f.params())
    summary = await _one(session,
        "SELECT COALESCE(SUM(receivable),0) AS receivable, COALESCE(SUM(payable),0) AS payable, "
        "COALESCE(SUM(net_balance),0) AS net FROM party_balance"
        + (" WHERE party_id = :party" if f.party_id is not None else ""), f.params())
    return {"summary": summary, "rows": rows}


async def party_sales(session, principal, f: Filters) -> dict:
    return await sales_by_party(session, principal, f)


async def party_purchase(session, principal, f: Filters) -> dict:
    return await purchase_by_party(session, principal, f)


async def payment_history(session, principal, f: Filters) -> dict:
    where = ("v.voucher_date BETWEEN :f AND :t"
             + _opt("v.party_id = :party", f.party_id)
             + _opt("v.branch_id = :branch", f.branch_id)
             + _opt("v.payment_type_id = :ptype", f.payment_type_id))
    rows = await _rows(session,
        f"SELECT v.doc_no, v.voucher_date AS date, v.voucher_type, pt.name AS party, "
        f"a.name AS account, ptp.name AS payment_type, v.amount, v.note, "
        f"(SELECT COALESCE(SUM(al.amount),0) FROM ledger_allocation al "
        f"  JOIN party_ledger_entry pe ON pe.id = al.settle_entry_id "
        f" WHERE pe.source_doc_type = 'payment_voucher' AND pe.source_doc_id = v.id) AS allocated "
        f"FROM payment_voucher v LEFT JOIN party pt ON pt.id = v.party_id "
        f"LEFT JOIN cash_bank_account a ON a.id = v.account_id "
        f"LEFT JOIN payment_type ptp ON ptp.id = v.payment_type_id "
        f"WHERE {where} ORDER BY v.voucher_date, v.id", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS vouchers, "
        f"COALESCE(SUM(v.amount) FILTER (WHERE v.voucher_type='receipt'),0) AS received, "
        f"COALESCE(SUM(v.amount) FILTER (WHERE v.voucher_type='payment'),0) AS paid "
        f"FROM payment_voucher v WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


# =====================================================================
# EXPENSES (v2 §6 — 4 reports)
# =====================================================================
def _expense_where(f: Filters) -> str:
    return ("e.expense_date BETWEEN :f AND :t"
            + _opt("e.branch_id = :branch", f.branch_id)
            + _opt("e.category_id = :category", f.category_id))


async def _expense_totals(session, f: Filters) -> dict:
    return await _one(session,
        f"SELECT COUNT(*) AS count, COALESCE(SUM(e.amount),0) AS total "
        f"FROM expense e WHERE {_expense_where(f)}", f.params())


async def expense_summary(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT e.expense_date AS date, COUNT(*) AS count, SUM(e.amount) AS amount "
        f"FROM expense e WHERE {_expense_where(f)} "
        f"GROUP BY e.expense_date ORDER BY e.expense_date", f.params())
    return {"summary": await _expense_totals(session, f), "rows": rows}


async def expense_detailed(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT e.doc_no, e.expense_date AS date, COALESCE(c.name,'Uncategorised') AS category, "
        f"br.name AS branch, a.name AS account, e.amount, e.note "
        f"FROM expense e LEFT JOIN expense_category c ON c.id = e.category_id "
        f"LEFT JOIN branch br ON br.id = e.branch_id "
        f"LEFT JOIN cash_bank_account a ON a.id = e.account_id "
        f"WHERE {_expense_where(f)} ORDER BY e.expense_date, e.id", f.params())
    return {"summary": await _expense_totals(session, f), "rows": rows}


async def expense_by_category(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT COALESCE(c.name,'Uncategorised') AS category, COUNT(*) AS count, "
        f"SUM(e.amount) AS amount FROM expense e "
        f"LEFT JOIN expense_category c ON c.id = e.category_id "
        f"WHERE {_expense_where(f)} GROUP BY c.name ORDER BY amount DESC", f.params())
    return {"summary": await _expense_totals(session, f), "rows": rows}


async def expense_by_branch(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT br.name AS branch, COUNT(*) AS count, SUM(e.amount) AS amount "
        f"FROM expense e LEFT JOIN branch br ON br.id = e.branch_id "
        f"WHERE {_expense_where(f)} GROUP BY br.name ORDER BY amount DESC", f.params())
    return {"summary": await _expense_totals(session, f), "rows": rows}


# =====================================================================
# SALE ORDER / DELIVERY (v2 §6 — 4 reports)
# =====================================================================
async def deliveries_pending(session, principal, f: Filters) -> dict:
    where = ("so.status IN ('pending','partial') AND so.order_date BETWEEN :f AND :t"
             + _opt("so.branch_id = :branch", f.branch_id)
             + _opt("so.customer_id = :party", f.party_id))
    rows = await _rows(session,
        f"SELECT so.doc_no, so.order_date AS date, pt.name AS party, pt.area, so.status, "
        f"so.grand_total, (CURRENT_DATE - so.order_date) AS age_days, "
        f"(SELECT COALESCE(SUM(sol.base_qty),0) FROM sale_order_line sol WHERE sol.order_id=so.id) "
        f"- (SELECT COALESCE(SUM(sf.moved_qty),0) FROM stock_fulfillment sf WHERE sf.sale_order_id=so.id) "
        f"  AS pending_qty "
        f"FROM sale_order so LEFT JOIN party pt ON pt.id = so.customer_id "
        f"WHERE {where} ORDER BY age_days DESC", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS pending_orders, COALESCE(SUM(so.grand_total),0) AS value "
        f"FROM sale_order so WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def deliveries_cancelled(session, principal, f: Filters) -> dict:
    where = ("so.status = 'cancelled' AND so.order_date BETWEEN :f AND :t"
             + _opt("so.branch_id = :branch", f.branch_id)
             + _opt("so.customer_id = :party", f.party_id))
    rows = await _rows(session,
        f"SELECT so.doc_no, so.order_date AS date, pt.name AS party, so.grand_total, so.note "
        f"FROM sale_order so LEFT JOIN party pt ON pt.id = so.customer_id "
        f"WHERE {where} ORDER BY so.order_date DESC", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS cancelled_orders, COALESCE(SUM(so.grand_total),0) AS value "
        f"FROM sale_order so WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def deliveries_by_branch(session, principal, f: Filters) -> dict:
    where = ("d.delivery_date BETWEEN :f AND :t" + _opt("d.branch_id = :branch", f.branch_id))
    rows = await _rows(session,
        f"SELECT br.name AS branch, d.status, COUNT(*) AS deliveries "
        f"FROM delivery d LEFT JOIN branch br ON br.id = d.branch_id "
        f"WHERE {where} GROUP BY br.name, d.status ORDER BY br.name, d.status", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS deliveries FROM delivery d WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


async def delivery_performance(session, principal, f: Filters) -> dict:
    """How long orders take to be delivered, by the staff who deliver them."""
    where = ("d.delivery_date BETWEEN :f AND :t" + _opt("d.branch_id = :branch", f.branch_id))
    rows = await _rows(session,
        f"SELECT COALESCE(u.full_name, u.username, 'Unassigned') AS delivery_staff, "
        f"COUNT(*) AS deliveries, "
        f"COUNT(*) FILTER (WHERE d.status = 'completed') AS completed, "
        f"ROUND(AVG(d.delivery_date - so.order_date)::numeric, 2) AS avg_days "
        f"FROM delivery d LEFT JOIN app_user u ON u.id = d.delivery_boy_id "
        f"LEFT JOIN sale_order so ON so.id = d.sale_order_id "
        f"WHERE {where} GROUP BY u.full_name, u.username ORDER BY deliveries DESC", f.params())
    summary = await _one(session,
        f"SELECT COUNT(*) AS deliveries, "
        f"COUNT(*) FILTER (WHERE d.status='completed') AS completed, "
        f"ROUND(AVG(d.delivery_date - so.order_date)::numeric, 2) AS avg_days "
        f"FROM delivery d LEFT JOIN sale_order so ON so.id = d.sale_order_id "
        f"WHERE {where}", f.params())
    return {"summary": summary, "rows": rows}


# =====================================================================
# PROFIT & LOSS (v2 §6 — 5 reports; decision #6: gross AND net)
# =====================================================================
async def _profit_totals(session, f: Filters) -> dict:
    tot = await _one(session,
        f"SELECT COALESCE(SUM(sbl.taxable),0) AS revenue, "
        f"COALESCE(SUM(sbl.cogs_amount),0) AS cogs "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id "
        f"WHERE {_sales_where(f)}", f.params())
    exp = await _one(session,
        f"SELECT COALESCE(SUM(e.amount),0) AS expenses FROM expense e "
        f"WHERE {_expense_where(f)}", f.params())
    revenue, cogs = Decimal(tot["revenue"]), Decimal(tot["cogs"])
    gross = revenue - cogs
    return {"revenue": str(revenue), "cogs": str(cogs), "gross_profit": str(gross),
            "expenses": exp["expenses"], "net_profit": str(gross - Decimal(exp["expenses"]))}


async def profit_loss(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT sb.bill_date AS date, SUM(sbl.taxable) AS revenue, "
        f"SUM(sbl.cogs_amount) AS cogs, SUM(sbl.taxable - sbl.cogs_amount) AS gross_profit "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id "
        f"WHERE {_sales_where(f)} GROUP BY sb.bill_date ORDER BY sb.bill_date", f.params())
    return {"summary": await _profit_totals(session, f), "rows": rows}


async def profit_by_bill(session, principal, f: Filters) -> dict:
    rows = await _rows(session,
        f"SELECT sb.doc_no, sb.bill_date AS date, pt.name AS party, "
        f"SUM(sbl.taxable) AS revenue, SUM(sbl.cogs_amount) AS cogs, "
        f"SUM(sbl.taxable - sbl.cogs_amount) AS gross_profit, "
        f"CASE WHEN SUM(sbl.taxable) > 0 THEN "
        f"  ROUND(100 * SUM(sbl.taxable - sbl.cogs_amount) / SUM(sbl.taxable), 2) END AS margin_pct "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id "
        f"LEFT JOIN party pt ON pt.id = sb.customer_id "
        f"WHERE {_sales_where(f)} GROUP BY sb.doc_no, sb.bill_date, pt.name "
        f"ORDER BY gross_profit DESC", f.params())
    return {"summary": await _profit_totals(session, f), "rows": rows}


async def _profit_grouped(session, f: Filters, select: str, join: str, group: str) -> dict:
    rows = await _rows(session,
        f"SELECT {select}, SUM(sbl.base_qty) AS qty, SUM(sbl.taxable) AS revenue, "
        f"SUM(sbl.cogs_amount) AS cogs, SUM(sbl.taxable - sbl.cogs_amount) AS gross_profit, "
        f"CASE WHEN SUM(sbl.taxable) > 0 THEN "
        f"  ROUND(100 * SUM(sbl.taxable - sbl.cogs_amount) / SUM(sbl.taxable), 2) END AS margin_pct "
        f"FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id = sbl.bill_id {join} "
        f"WHERE {_sales_where(f)}"
        + _opt("pr.category_id = :category", f.category_id)
        + f" GROUP BY {group} ORDER BY gross_profit DESC NULLS LAST", f.params())
    return {"summary": await _profit_totals(session, f), "rows": rows}


async def profit_by_product(session, principal, f: Filters) -> dict:
    return await _profit_grouped(session, f, "pr.code, pr.name AS product",
                                 "JOIN product pr ON pr.id = sbl.product_id", "pr.code, pr.name")


async def profit_by_category(session, principal, f: Filters) -> dict:
    return await _profit_grouped(session, f, "COALESCE(c.name,'Uncategorised') AS category",
                                 "JOIN product pr ON pr.id = sbl.product_id "
                                 "LEFT JOIN product_category c ON c.id = pr.category_id", "c.name")


async def profit_by_party(session, principal, f: Filters) -> dict:
    return await _profit_grouped(session, f, "pt.party_code, pt.name AS party",
                                 "JOIN product pr ON pr.id = sbl.product_id "
                                 "LEFT JOIN party pt ON pt.id = sb.customer_id",
                                 "pt.party_code, pt.name")


# =====================================================================
# Registry — key -> (group, title, fn). The API serves this as a catalogue
# so the UI's picker is data, not a hard-coded list.
# =====================================================================
REPORTS: dict[str, tuple[str, str, object]] = {
    # Sales
    "sales_summary": ("Sales", "Sales Summary", sales_summary),
    "sales_detailed": ("Sales", "Sales Detailed", sales_detailed),
    "sales_product": ("Sales", "Product-wise Sales", sales_by_product),
    "sales_party": ("Sales", "Party-wise Sales", sales_by_party),
    "sales_category": ("Sales", "Category-wise Sales", sales_by_category),
    "sales_branch": ("Sales", "Branch-wise Sales", sales_by_branch),
    "sales_payment_mode": ("Sales", "Payment Mode-wise Sales", sales_by_payment_mode),
    "sales_gst": ("Sales", "GST Sales Report", sales_gst),
    "sales_returns": ("Sales", "Sales Return Report", sales_returns),
    "sales_orders": ("Sales", "Sales Order Report", sales_orders),
    # Purchase
    "purchase_summary": ("Purchase", "Purchase Summary", purchase_summary),
    "purchase_detailed": ("Purchase", "Purchase Details", purchase_detailed),
    "purchase_product": ("Purchase", "Product-wise Purchase", purchase_by_product),
    "purchase_party": ("Purchase", "Party-wise Purchase", purchase_by_party),
    "purchase_category": ("Purchase", "Category-wise Purchase", purchase_by_category),
    "purchase_branch": ("Purchase", "Branch-wise Purchase", purchase_by_branch),
    "purchase_gst": ("Purchase", "GST Purchase Report", purchase_gst),
    "purchase_returns": ("Purchase", "Purchase Return Report", purchase_returns),
    "purchase_orders": ("Purchase", "Purchase Order Report", purchase_orders),
    # Stock
    "stock_current": ("Stock", "Current Stock", stock_current),
    "stock_branch": ("Stock", "Branch-wise Stock", stock_by_branch),
    "stock_godown": ("Stock", "Godown-wise Stock", stock_by_godown),
    "stock_product": ("Stock", "Product-wise Stock", stock_by_product),
    "stock_category": ("Stock", "Category-wise Stock", stock_by_category),
    "stock_value": ("Stock", "Stock Value", stock_value),
    "stock_low": ("Stock", "Low Stock Report", stock_low),
    "stock_zero": ("Stock", "Zero Stock Report", stock_zero),
    "stock_movement": ("Stock", "Stock Movement Report", stock_movement),
    "stock_adjustments": ("Stock", "Stock Adjustment Report", stock_adjustments),
    "stock_verifications": ("Stock", "Stock Verification Report", stock_verifications),
    # Party
    "party_ledger": ("Party", "Party Ledger", party_ledger),
    "party_outstanding": ("Party", "Outstanding Report", party_outstanding),
    "party_sales": ("Party", "Party Sales Report", party_sales),
    "party_purchase": ("Party", "Party Purchase Report", party_purchase),
    "party_payments": ("Party", "Payment History", payment_history),
    # Expenses
    "expense_summary": ("Expense", "Expense Summary", expense_summary),
    "expense_detailed": ("Expense", "Expense Details", expense_detailed),
    "expense_category": ("Expense", "Category-wise Expenses", expense_by_category),
    "expense_branch": ("Expense", "Branch-wise Expenses", expense_by_branch),
    # Sale orders / delivery
    "delivery_pending": ("Delivery", "Pending Deliveries", deliveries_pending),
    "delivery_cancelled": ("Delivery", "Cancelled Deliveries", deliveries_cancelled),
    "delivery_branch": ("Delivery", "Branch-wise Deliveries", deliveries_by_branch),
    "delivery_performance": ("Delivery", "Delivery Performance", delivery_performance),
    # Profit & loss
    "profit_loss": ("Profit", "Profit / Loss", profit_loss),
    "profit_bill": ("Profit", "Bill-wise Profit / Loss", profit_by_bill),
    "profit_product": ("Profit", "Product-wise Profit", profit_by_product),
    "profit_category": ("Profit", "Category-wise Profit", profit_by_category),
    "profit_party": ("Profit", "Party-wise Profit", profit_by_party),
}


def catalogue() -> list[dict]:
    return [{"key": k, "group": g, "title": t} for k, (g, t, _) in REPORTS.items()]
