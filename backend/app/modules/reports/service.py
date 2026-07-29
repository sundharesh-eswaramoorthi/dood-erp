"""Reports — date-range aggregations over the ledgers/documents.

Each returns {"summary": {...}, "rows": [...]}. Figures respect RLS via the
scoped session. Profit uses the COGS snapshot stored on each sales_bill_line
(decision #6: gross = revenue - COGS, net = gross - expenses).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal


async def _rows(session, sql, **p):
    return [dict(r) for r in (await session.execute(text(sql), p)).mappings().all()]


async def _one(session, sql, **p):
    return dict((await session.execute(text(sql), p)).mappings().one())


async def sales(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    p = {"f": dfrom, "t": dto}
    rows = await _rows(session,
        "SELECT sb.doc_no, sb.bill_date, pt.name AS customer, sb.taxable_total, sb.tax_total, sb.grand_total "
        "FROM sales_bill sb LEFT JOIN party pt ON pt.id=sb.customer_id "
        "WHERE sb.bill_date BETWEEN :f AND :t ORDER BY sb.bill_date, sb.id", **p)
    summary = await _one(session,
        "SELECT COUNT(*) AS bills, COALESCE(SUM(taxable_total),0) AS taxable, "
        "COALESCE(SUM(tax_total),0) AS tax, COALESCE(SUM(grand_total),0) AS total "
        "FROM sales_bill WHERE bill_date BETWEEN :f AND :t", **p)
    return {"summary": summary, "rows": rows}


async def purchase(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    p = {"f": dfrom, "t": dto}
    rows = await _rows(session,
        "SELECT pb.doc_no, pb.bill_date, pt.name AS supplier, pb.taxable_total, pb.tax_total, pb.grand_total "
        "FROM purchase_bill pb LEFT JOIN party pt ON pt.id=pb.supplier_id "
        "WHERE pb.bill_date BETWEEN :f AND :t ORDER BY pb.bill_date, pb.id", **p)
    summary = await _one(session,
        "SELECT COUNT(*) AS bills, COALESCE(SUM(taxable_total),0) AS taxable, "
        "COALESCE(SUM(tax_total),0) AS tax, COALESCE(SUM(grand_total),0) AS total "
        "FROM purchase_bill WHERE bill_date BETWEEN :f AND :t", **p)
    return {"summary": summary, "rows": rows}


async def stock(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    # current valuation snapshot (date-independent)
    rows = await _rows(session,
        "SELECT p.code, p.name, COALESCE(SUM(b.on_hand),0) AS on_hand, "
        "COALESCE(MAX(pc.moving_avg_cost),0) AS avg_cost, "
        "COALESCE(SUM(b.on_hand),0) * COALESCE(MAX(pc.moving_avg_cost),0) AS value "
        "FROM product p "
        "LEFT JOIN stock_balance b ON b.product_id=p.id AND b.location_state='on_hand' "
        "LEFT JOIN product_cost pc ON pc.product_id=p.id "
        "GROUP BY p.id, p.code, p.name HAVING COALESCE(SUM(b.on_hand),0) <> 0 ORDER BY value DESC")
    total = sum((r["value"] for r in rows), start=0)
    return {"summary": {"products": len(rows), "total_value": total}, "rows": rows}


async def party(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    rows = await _rows(session,
        "SELECT pt.name, pb.receivable, pb.payable, pb.net_balance FROM party_balance pb "
        "JOIN party pt ON pt.id=pb.party_id WHERE pb.net_balance <> 0 ORDER BY pb.net_balance DESC")
    summary = await _one(session,
        "SELECT COALESCE(SUM(receivable),0) AS receivable, COALESCE(SUM(payable),0) AS payable FROM party_balance")
    return {"summary": summary, "rows": rows}


async def expense(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    p = {"f": dfrom, "t": dto}
    rows = await _rows(session,
        "SELECT COALESCE(c.name,'Uncategorised') AS category, COUNT(*) AS count, SUM(e.amount) AS amount "
        "FROM expense e LEFT JOIN expense_category c ON c.id=e.category_id "
        "WHERE e.expense_date BETWEEN :f AND :t GROUP BY c.name ORDER BY amount DESC", **p)
    total = await _one(session,
        "SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expense WHERE expense_date BETWEEN :f AND :t", **p)
    return {"summary": total, "rows": rows}


async def delivery(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    p = {"f": dfrom, "t": dto}
    rows = await _rows(session,
        "SELECT status, COUNT(*) AS count FROM delivery WHERE delivery_date BETWEEN :f AND :t "
        "GROUP BY status ORDER BY status", **p)
    total = await _one(session,
        "SELECT COUNT(*) AS deliveries FROM delivery WHERE delivery_date BETWEEN :f AND :t", **p)
    return {"summary": total, "rows": rows}


async def profit(session: AsyncSession, principal: Principal, dfrom, dto) -> dict:
    p = {"f": dfrom, "t": dto}
    # per-product revenue/COGS
    rows = await _rows(session,
        "SELECT pr.name, SUM(sbl.taxable) AS revenue, SUM(sbl.cogs_amount) AS cogs, "
        "SUM(sbl.taxable) - SUM(sbl.cogs_amount) AS gross_profit "
        "FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id=sbl.bill_id "
        "JOIN product pr ON pr.id=sbl.product_id "
        "WHERE sb.bill_date BETWEEN :f AND :t GROUP BY pr.name ORDER BY gross_profit DESC", **p)
    tot = await _one(session,
        "SELECT COALESCE(SUM(sbl.taxable),0) AS revenue, COALESCE(SUM(sbl.cogs_amount),0) AS cogs "
        "FROM sales_bill_line sbl JOIN sales_bill sb ON sb.id=sbl.bill_id WHERE sb.bill_date BETWEEN :f AND :t", **p)
    expenses = await _one(session,
        "SELECT COALESCE(SUM(amount),0) AS expenses FROM expense WHERE expense_date BETWEEN :f AND :t", **p)
    gross = tot["revenue"] - tot["cogs"]
    net = gross - expenses["expenses"]
    return {"summary": {"revenue": tot["revenue"], "cogs": tot["cogs"], "gross_profit": gross,
                        "expenses": expenses["expenses"], "net_profit": net}, "rows": rows}


REPORTS = {
    "sales": sales, "purchase": purchase, "stock": stock, "party": party,
    "expense": expense, "delivery": delivery, "profit": profit,
}
