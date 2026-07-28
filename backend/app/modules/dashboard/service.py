"""Dashboard widgets — computed from the ledgers, Redis-cached (short TTL).

Read-heavy, so it is cached in Redis for ~30s per (org, branch); the outbox
drainer could bust it on writes, but the short TTL keeps it simple here. All
figures respect RLS via the scoped session (branch tables auto-scope).
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import redis_client
from app.core.deps import Principal

_TTL = 30  # seconds


async def _scalar(session, sql, **params):
    return (await session.execute(text(sql), params)).scalar_one()


async def get_dashboard(session: AsyncSession, principal: Principal, branch_id: int) -> dict:
    key = f"dash:{principal.org_id}:{branch_id}"
    cached = await redis_client.get(key)
    if cached:
        data = json.loads(cached)
        data["cached"] = True
        return data

    today = dt.date.today()  # a date object — asyncpg binds DATE params, not strings
    p = {"t": today}

    today_sales = await _scalar(session, "SELECT COALESCE(SUM(grand_total),0) FROM sales_bill WHERE bill_date=:t", **p)
    today_purchase = await _scalar(session, "SELECT COALESCE(SUM(grand_total),0) FROM purchase_bill WHERE bill_date=:t", **p)
    today_orders = await _scalar(session, "SELECT COUNT(*) FROM sale_order WHERE order_date=:t", **p)
    pending_deliveries = await _scalar(session, "SELECT COUNT(*) FROM sale_order WHERE status='pending'")
    today_collection = await _scalar(session, "SELECT COALESCE(SUM(amount),0) FROM payment_voucher WHERE voucher_type='receipt' AND voucher_date=:t", **p)
    today_expenses = await _scalar(session, "SELECT COALESCE(SUM(amount),0) FROM expense WHERE expense_date=:t", **p)
    stock_value = await _scalar(
        session,
        "SELECT COALESCE(SUM(b.on_hand * COALESCE(pc.moving_avg_cost,0)),0) FROM stock_balance b "
        "LEFT JOIN product_cost pc ON pc.org_id=b.org_id AND pc.product_id=b.product_id AND pc.branch_id=b.branch_id "
        "WHERE b.location_state='on_hand'",
    )
    receivable = await _scalar(session, "SELECT COALESCE(SUM(receivable),0) FROM party_balance")
    payable = await _scalar(session, "SELECT COALESCE(SUM(payable),0) FROM party_balance")
    petty_cash = await _scalar(session, "SELECT COALESCE(SUM(current_balance),0) FROM cash_bank_account WHERE account_type='petty_cash'")

    low_stock = (
        await session.execute(text(
            "SELECT p.name, COALESCE(sb.oh,0) AS on_hand, rt.min_qty FROM reorder_threshold rt "
            "JOIN product p ON p.id=rt.product_id "
            "LEFT JOIN (SELECT product_id, SUM(on_hand) oh FROM stock_balance WHERE location_state='on_hand' GROUP BY product_id) sb "
            "  ON sb.product_id=rt.product_id "
            "WHERE COALESCE(sb.oh,0) < rt.min_qty ORDER BY (rt.min_qty - COALESCE(sb.oh,0)) DESC LIMIT 10"
        ))
    ).mappings().all()

    top_selling = (
        await session.execute(text(
            "SELECT p.name, SUM(sbl.base_qty) AS qty FROM sales_bill_line sbl "
            "JOIN product p ON p.id=sbl.product_id GROUP BY p.name ORDER BY qty DESC LIMIT 5"
        ))
    ).mappings().all()

    raw_activity = await redis_client.lrange(f"recent_activity:{principal.org_id}", 0, 7)
    recent = [json.loads(a) for a in raw_activity]

    data = {
        "today_sales": today_sales, "today_purchase": today_purchase, "today_orders": today_orders,
        "pending_deliveries": pending_deliveries, "today_collection": today_collection,
        "today_expenses": today_expenses, "current_stock_value": stock_value,
        "outstanding_receivable": receivable, "outstanding_payable": payable, "petty_cash": petty_cash,
        "low_stock": [dict(r) for r in low_stock],
        "top_selling": [dict(r) for r in top_selling],
        "recent_activities": recent,
        "cached": False,
    }
    await redis_client.set(key, json.dumps(data, default=str), ex=_TTL)
    return data
