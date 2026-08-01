"""Party ledger posting primitive (Phase-2 design).

Invariant: party_balance.net_balance == SUM(debit) - SUM(credit) per party.
The entry row and the balance update commit in the same transaction, under a
row lock on the balance. Bills/receipts in later phases post through this.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def post_entry(
    session: AsyncSession,
    *,
    org_id: int,
    branch_id: int,
    party_id: int,
    entry_side: str,          # 'debit' (they owe us) | 'credit' (we owe them)
    amount: Decimal,
    source: tuple[str, int, int],
    effective_date,
    created_by: int,
    gst_registration_id: int | None = None,
    entry_purpose: str = "original",
    reversal_seq: int = 0,
) -> tuple[int, Decimal]:
    """Returns (entry_id, new_net_balance).

    The entry id is what app.services.allocation needs to settle this entry
    against specific invoices — party_balance alone can only say how much is
    owed, not against what.

    entry_purpose/reversal_seq let a caller correct an already-posted figure
    without mutating history: post the reversal, then the replacement, both
    under the same source doc but a fresh seq (uq_party_ledger_source)."""
    src_type, src_id, line_no = source
    entry_id = (await session.execute(
        text(
            "INSERT INTO party_ledger_entry "
            "(org_id, branch_id, party_id, gst_registration_id, entry_side, amount, "
            " source_doc_type, source_doc_id, source_line_no, entry_purpose, reversal_seq, "
            " effective_date, created_by) "
            "VALUES (:o, :b, :p, :gr, :sd, :amt, :st, :sid, :ln, :pur, :seq, :ed, :by) "
            "RETURNING id"
        ),
        {"o": org_id, "b": branch_id, "p": party_id, "gr": gst_registration_id, "sd": entry_side,
         "amt": amount, "st": src_type, "sid": src_id, "ln": line_no, "pur": entry_purpose,
         "seq": reversal_seq, "ed": effective_date, "by": created_by},
    )).scalar_one()
    # ensure + lock the balance row
    await session.execute(
        text("INSERT INTO party_balance (org_id, party_id) VALUES (:o, :p) ON CONFLICT DO NOTHING"),
        {"o": org_id, "p": party_id},
    )
    net = Decimal(
        (
            await session.execute(
                text("SELECT net_balance FROM party_balance WHERE org_id=:o AND party_id=:p FOR UPDATE"),
                {"o": org_id, "p": party_id},
            )
        ).scalar_one()
    )
    net += amount if entry_side == "debit" else -amount
    receivable = net if net > 0 else Decimal(0)
    payable = -net if net < 0 else Decimal(0)
    await session.execute(
        text(
            "UPDATE party_balance SET net_balance=:n, receivable=:recv, payable=:pay, "
            "version=version+1, updated_at=now() WHERE org_id=:o AND party_id=:p"
        ),
        {"n": net, "recv": receivable, "pay": payable, "o": org_id, "p": party_id},
    )
    return entry_id, net
