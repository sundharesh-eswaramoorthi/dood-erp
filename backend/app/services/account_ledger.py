"""Cash/bank account posting primitive.

Invariant: cash_bank_account.current_balance == opening + SUM(in) - SUM(out).
The entry row and the balance update commit together under a row lock.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def post_account_entry(
    session: AsyncSession, *, org_id: int, account_id: int, direction: str,
    amount: Decimal, source: tuple[str, int, int], effective_date, created_by: int,
    entry_purpose: str = "original", reversal_seq: int = 0,
) -> Decimal:
    """entry_purpose/reversal_seq let app.services.reversal negate a posting
    without touching the original row (the ledger is append-only)."""
    src_type, src_id, line_no = source
    await session.execute(
        text(
            "INSERT INTO account_ledger_entry (org_id, account_id, direction, amount, "
            "source_doc_type, source_doc_id, source_line_no, entry_purpose, reversal_seq, "
            "effective_date, created_by) "
            "VALUES (:o,:a,:d,:amt,:st,:sid,:ln,:pur,:seq,:ed,:by)"
        ),
        {"o": org_id, "a": account_id, "d": direction, "amt": amount, "st": src_type,
         "sid": src_id, "ln": line_no, "pur": entry_purpose, "seq": reversal_seq,
         "ed": effective_date, "by": created_by},
    )
    cur = Decimal(
        (
            await session.execute(
                text("SELECT current_balance FROM cash_bank_account WHERE org_id=:o AND id=:a FOR UPDATE"),
                {"o": org_id, "a": account_id},
            )
        ).scalar_one()
    )
    cur += amount if direction == "in" else -amount
    await session.execute(
        text("UPDATE cash_bank_account SET current_balance=:c, version=version+1 WHERE org_id=:o AND id=:a"),
        {"c": cur, "o": org_id, "a": account_id},
    )
    return cur
