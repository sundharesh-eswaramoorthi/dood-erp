"""Glue between app.services.money (pure arithmetic) and the document tables.

Keeps the four posting services from each hand-rolling the same UPDATE and the
same paid-at-bill-time postings — which is exactly where purchase and sales
drifted apart before v2.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.account_ledger import post_account_entry
from app.services.money import Totals
from app.services.party_ledger import post_entry as post_party_entry


async def resolve_godown(
    session: AsyncSession, branch_id: int, line_godown: int | None, header_godown: int | None
) -> int:
    """A line's godown, defaulting to the header's, validated against the branch."""
    godown_id = line_godown or header_godown
    if godown_id is None:
        raise ValueError("every line needs a godown (set it on the line or on the document)")
    ok = (
        await session.execute(
            text("SELECT 1 FROM godown WHERE id=:g AND branch_id=:b AND is_active"),
            {"g": godown_id, "b": branch_id},
        )
    ).scalar_one_or_none()
    if ok is None:
        raise ValueError(f"godown {godown_id} is not an active godown of branch {branch_id}")
    return godown_id


async def product_hsn(session: AsyncSession, product_id: int) -> str | None:
    return (
        await session.execute(text("SELECT hsn_code FROM product WHERE id=:p"), {"p": product_id})
    ).scalar_one_or_none()


async def write_totals(session: AsyncSession, table: str, doc_id: int, t: Totals) -> None:
    """Stamp the computed money block onto the document header."""
    await session.execute(
        text(
            f"UPDATE {table} SET gross_total=:gr, line_discount_total=:ld, discount_amount=:hd, "
            "taxable_total=:tx, tax_total=:tax, card_charges=:cc, round_off=:ro, "
            "grand_total=:gt, paid_amount=:paid, balance_amount=:bal WHERE id=:i"
        ),
        {"gr": t.gross_total, "ld": t.line_discount_total, "hd": t.header_discount,
         "tx": t.taxable_total, "tax": t.tax_total, "cc": t.card_charges, "ro": t.round_off,
         "gt": t.grand_total, "paid": t.paid_amount, "bal": t.balance_amount, "i": doc_id},
    )


async def settle_at_post(
    session: AsyncSession,
    *,
    org_id: int,
    branch_id: int,
    party_id: int,
    account_id: int | None,
    doc_type: str,
    doc_id: int,
    amount: Decimal,
    effective_date,
    created_by: int,
    party_side: str,
    account_direction: str,
) -> None:
    """Money handed over at the moment the invoice is raised (v2 "Paid Amount").

    Without this the party would owe the full grand total while the cash had
    already moved, so the receivable and the bank would both be wrong. The
    settlement posts under its own source_doc_type so it never collides with
    the invoice's own ledger row.

    party_side/account_direction are 'credit'+'in' for a sales bill (customer
    pays us) and 'debit'+'out' for a purchase bill (we pay the supplier).
    """
    if amount <= 0:
        return
    if account_id is None:
        raise ValueError("paid_amount needs a payment_account_id (which cash/bank account)")
    ok = (
        await session.execute(
            text("SELECT 1 FROM cash_bank_account WHERE id=:a AND org_id=:o AND is_active"),
            {"a": account_id, "o": org_id},
        )
    ).scalar_one_or_none()
    if ok is None:
        raise ValueError(f"payment account {account_id} not found")

    await post_party_entry(
        session, org_id=org_id, branch_id=branch_id, party_id=party_id,
        entry_side=party_side, amount=amount,
        source=(f"{doc_type}_payment", doc_id, 0),
        effective_date=effective_date, created_by=created_by,
    )
    await post_account_entry(
        session, org_id=org_id, account_id=account_id, direction=account_direction,
        amount=amount, source=(f"{doc_type}_payment", doc_id, 0),
        effective_date=effective_date, created_by=created_by,
    )
