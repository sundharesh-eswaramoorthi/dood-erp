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


async def validate_header_godown(
    session: AsyncSession, branch_id: int, header_godown: int | None
) -> None:
    """Check the document's DEFAULT godown, which is stored on the header.

    resolve_godown only ever sees it when a line falls back to it, so a header
    godown belonging to another branch was accepted and written down whenever
    every line named its own. It does not stay harmless: a purchase order's
    header godown is read back at receive time and becomes the bill's default,
    so the refusal arrived against the bill instead of the order that was
    actually wrong.
    """
    if header_godown is not None:
        await resolve_godown(session, branch_id, None, header_godown)


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
    doc_type: str,
    doc_id: int,
    splits,
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

    `splits` is a list of tenders (v2 §3): part cash, part UPI, part card is one
    invoice, not three.

    The party gets ONE entry for the whole amount — a customer statement should
    read "paid ₹5000 against SB-0007", not three lines describing which of our
    bank accounts the money reached; that is our bookkeeping, not their debt.
    The accounts get one entry EACH, because the cash genuinely landed in
    different places, keyed by seq as source_line_no so their unique keys stay
    distinct and the existing reversal negates every leg unaided.

    party_side/account_direction are 'credit'+'in' for a sales bill (customer
    pays us) and 'debit'+'out' for a purchase bill (we pay the supplier).
    """
    if not splits:
        return
    src = f"{doc_type}_payment"
    total = sum((s.amount for s in splits), Decimal(0))

    await post_party_entry(
        session, org_id=org_id, branch_id=branch_id, party_id=party_id,
        entry_side=party_side, amount=total,
        source=(src, doc_id, 0),
        effective_date=effective_date, created_by=created_by,
    )
    for seq, split in enumerate(splits):
        ok = (
            await session.execute(
                text("SELECT 1 FROM cash_bank_account WHERE id=:a AND org_id=:o AND is_active"),
                {"a": split.account_id, "o": org_id},
            )
        ).scalar_one_or_none()
        if ok is None:
            raise ValueError(f"payment account {split.account_id} not found")
        if split.payment_type_id is not None:
            ok = (
                await session.execute(
                    text("SELECT 1 FROM payment_type WHERE id=:p AND org_id=:o AND is_active"),
                    {"p": split.payment_type_id, "o": org_id},
                )
            ).scalar_one_or_none()
            if ok is None:
                raise ValueError(f"payment type {split.payment_type_id} not found")

        await post_account_entry(
            session, org_id=org_id, account_id=split.account_id, direction=account_direction,
            amount=split.amount, source=(src, doc_id, seq),
            effective_date=effective_date, created_by=created_by,
        )
        # The tender itself, so payment-mode reports and the reprint can say
        # how the money actually arrived rather than only where it landed.
        await session.execute(
            text(
                "INSERT INTO document_payment "
                "(org_id, branch_id, doc_type, doc_id, seq, account_id, payment_type_id, "
                " amount, reference) "
                "VALUES (:o,:b,:dt,:di,:s,:a,:pt,:amt,:ref)"
            ),
            {"o": org_id, "b": branch_id, "dt": doc_type, "di": doc_id, "s": seq,
             "a": split.account_id, "pt": split.payment_type_id, "amt": split.amount,
             "ref": split.reference},
        )

    # Money handed over with the invoice settles THAT invoice. Leaving it
    # unallocated would show the bill as fully outstanding while the party
    # balance already reflected the cash (v2 §3 payment history).
    from app.services import allocation as alloc  # local import: avoids a cycle

    await alloc.settle_own_document(session, org_id, doc_type, doc_id)
