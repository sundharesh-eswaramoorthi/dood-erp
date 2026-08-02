"""Undo a posted document without rewriting history (v2 §7).

Everything this system posts is append-only: the stock ledger has an
immutability trigger, the party and account ledgers likewise. So "cancel this
invoice" cannot be an UPDATE or a DELETE. It is a second set of entries that
exactly negate the first, tagged entry_purpose='reversal' and pointing back at
what they undo.

That is why every ledger has carried entry_purpose / reversal_seq /
reverses_entry_id since the Phase-2 design — this module is what finally uses
them.

An amendment is this plus a re-post: reverse the original, post a new revision,
link the two. The old document stays readable at its original number, marked
cancelled and superseded, which is what an auditor expects to find.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.services import stock_engine as eng
from app.services.account_ledger import post_account_entry
from app.services.party_ledger import post_entry as post_party_entry

# doc_type -> the party side its ORIGINAL entry uses
PARTY_SIDE = {
    "purchase_bill": "credit",     # we owe the supplier
    "purchase_return": "debit",
    "sales_bill": "debit",         # the customer owes us
    "sales_return": "credit",
}
DATE_COL = {
    "purchase_bill": "bill_date",
    "purchase_return": "return_date",
    "sales_bill": "bill_date",
    "sales_return": "return_date",
}


class NotReversible(ValueError):
    """The document cannot be reversed in its current state."""


async def _next_seq(session: AsyncSession, table: str, org_id: int, doc_type: str, doc_id: int) -> int:
    """One seq per reversal round, shared by every line of the document."""
    return int(
        (await session.execute(
            text(f"SELECT COALESCE(MAX(reversal_seq), 0) + 1 FROM {table} "
                 "WHERE org_id=:o AND source_doc_type=:t AND source_doc_id=:i"),
            {"o": org_id, "t": doc_type, "i": doc_id},
        )).scalar_one()
    )


async def load_document(session: AsyncSession, doc_type: str, doc_id: int) -> dict:
    if doc_type not in PARTY_SIDE:
        raise NotReversible(f"{doc_type} cannot be amended")
    row = (
        await session.execute(text(f"SELECT * FROM {doc_type} WHERE id=:i"), {"i": doc_id})
    ).mappings().one_or_none()
    if row is None:
        raise LookupError(f"{doc_type} {doc_id} not found")
    return dict(row)


def assert_amendable(doc: dict, doc_type: str) -> None:
    if doc.get("status") == "cancelled":
        raise NotReversible("This document has already been cancelled")
    if doc.get("superseded_by"):
        raise NotReversible(
            f"This document was already amended — see revision #{doc['superseded_by']}"
        )


async def _reverse_stock(
    session: AsyncSession, principal: Principal, doc_type: str, doc_id: int, seq: int
) -> int:
    """Post the mirror image of every stock movement this document made."""
    rows = (
        await session.execute(
            text(
                "SELECT id, branch_id, godown_id, product_id, signed_qty, unit_cost, "
                "       movement_type, location_state, source_line_no "
                "FROM stock_movement_ledger "
                "WHERE org_id=:o AND source_doc_type=:t AND source_doc_id=:i "
                "  AND entry_purpose='original' ORDER BY id"
            ),
            {"o": principal.org_id, "t": doc_type, "i": doc_id},
        )
    ).mappings().all()

    for r in rows:
        qty = Decimal(r["signed_qty"])
        cost = Decimal(r["unit_cost"]) if r["unit_cost"] is not None else None
        # goods that went out come back at the cost they left at, and vice
        # versa, so the moving average lands where it started
        allow_neg = await eng.product_allows_negative(session, r["product_id"])
        await eng.move_stock(
            session, org_id=principal.org_id, branch_id=r["branch_id"],
            godown_id=r["godown_id"], product_id=r["product_id"],
            signed_qty=-qty, movement_type=r["movement_type"], cost=cost,
            source=(doc_type, doc_id, r["source_line_no"]),
            effective_date=dt.date.today(), created_by=principal.user_id,
            location_state=r["location_state"], allow_negative=allow_neg,
            entry_purpose="reversal", reversal_seq=seq,
        )
        # Undoing the moving average has to remove the value at the cost that
        # went IN, not at today's average. apply_cost_outbound drops qty_basis
        # while leaving the average untouched, so using it here would strand
        # the purchase's cost in the valuation for ever.
        if qty > 0 and cost is not None:
            # original was goods-in: subtract that qty at that cost
            await eng.apply_cost_inbound(
                session, principal.org_id, r["product_id"], r["branch_id"], -qty, cost
            )
        elif qty > 0:
            await eng.apply_cost_outbound(
                session, principal.org_id, r["product_id"], r["branch_id"], qty
            )
        elif cost is not None:
            # original was goods-out: put it back at the cost it left at
            await eng.apply_cost_inbound(
                session, principal.org_id, r["product_id"], r["branch_id"], -qty, cost
            )
    return len(rows)


async def _reverse_party(
    session: AsyncSession, principal: Principal, doc_type: str, doc_id: int
) -> int:
    """Negate the receivable/payable, and any money taken with the document.

    Allocations pointing at those entries are removed: an allocation is a live
    mapping of what settles what, not a ledger, and once the invoice is void
    the mapping is meaningless. The settling payment itself is untouched and
    simply becomes unallocated again.
    """
    count = 0
    for src in (doc_type, f"{doc_type}_payment"):
        rows = (
            await session.execute(
                text(
                    "SELECT id, branch_id, party_id, entry_side, amount, source_line_no "
                    "FROM party_ledger_entry WHERE org_id=:o AND source_doc_type=:t "
                    "AND source_doc_id=:i AND entry_purpose='original' ORDER BY id"
                ),
                {"o": principal.org_id, "t": src, "i": doc_id},
            )
        ).mappings().all()
        if not rows:
            continue
        seq = await _next_seq(session, "party_ledger_entry", principal.org_id, src, doc_id)
        for r in rows:
            await session.execute(
                text("DELETE FROM ledger_allocation WHERE org_id=:o "
                     "AND (against_entry_id=:e OR settle_entry_id=:e)"),
                {"o": principal.org_id, "e": r["id"]},
            )
            await post_party_entry(
                session, org_id=principal.org_id, branch_id=r["branch_id"],
                party_id=r["party_id"],
                entry_side="credit" if r["entry_side"] == "debit" else "debit",
                amount=Decimal(r["amount"]), source=(src, doc_id, r["source_line_no"]),
                effective_date=dt.date.today(), created_by=principal.user_id,
                entry_purpose="reversal", reversal_seq=seq,
            )
            count += 1
    return count


async def _reverse_account(
    session: AsyncSession, principal: Principal, doc_type: str, doc_id: int
) -> int:
    src = f"{doc_type}_payment"
    rows = (
        await session.execute(
            text("SELECT id, account_id, direction, amount, source_line_no "
                 "FROM account_ledger_entry WHERE org_id=:o AND source_doc_type=:t "
                 "AND source_doc_id=:i AND entry_purpose='original' ORDER BY id"),
            {"o": principal.org_id, "t": src, "i": doc_id},
        )
    ).mappings().all()
    if not rows:
        return 0
    seq = await _next_seq(session, "account_ledger_entry", principal.org_id, src, doc_id)
    for r in rows:
        await post_account_entry(
            session, org_id=principal.org_id, account_id=r["account_id"],
            direction="out" if r["direction"] == "in" else "in",
            amount=Decimal(r["amount"]), source=(src, doc_id, r["source_line_no"]),
            effective_date=dt.date.today(), created_by=principal.user_id,
            entry_purpose="reversal", reversal_seq=seq,
        )
    return len(rows)


async def reverse_document(
    session: AsyncSession,
    principal: Principal,
    doc_type: str,
    doc_id: int,
    *,
    reason: str | None = None,
    action: str = "cancel",
    replaced_by: int | None = None,
) -> dict:
    """Negate every effect this document had, then mark it cancelled."""
    doc = await load_document(session, doc_type, doc_id)
    assert_amendable(doc, doc_type)

    stock_seq = await _next_seq(session, "stock_movement_ledger", principal.org_id, doc_type, doc_id)
    moved = await _reverse_stock(session, principal, doc_type, doc_id, stock_seq)
    party = await _reverse_party(session, principal, doc_type, doc_id)
    acct = await _reverse_account(session, principal, doc_type, doc_id)

    # The tender breakdown describes money this document took. The account
    # entries above have been negated, so leaving these would keep a cancelled
    # invoice showing in the payment-mode reports. Like ledger_allocation, this
    # is a live description rather than a ledger, so it is deleted, not negated.
    await session.execute(
        text("DELETE FROM document_payment WHERE org_id=:o AND doc_type=:t AND doc_id=:i"),
        {"o": principal.org_id, "t": doc_type, "i": doc_id},
    )

    # a sales bill that moved stock recorded fulfilment against its order;
    # once reversed the order is unfulfilled again
    if doc_type == "sales_bill":
        await session.execute(
            text("DELETE FROM stock_fulfillment WHERE org_id=:o "
                 "AND moved_by_doc_type='sales_bill' AND moved_by_doc_id=:i"),
            {"o": principal.org_id, "i": doc_id},
        )

    await session.execute(
        text(f"UPDATE {doc_type} SET status='cancelled', cancelled_at=now(), "
             "cancelled_by=:by, cancel_reason=:r WHERE id=:i"),
        {"by": principal.user_id, "r": reason, "i": doc_id},
    )
    await session.execute(
        text("INSERT INTO document_amendment (org_id, branch_id, doc_type, doc_id, action, "
             "replaced_by, reason, doc_date, created_by) "
             "VALUES (:o,:b,:t,:i,:a,:rep,:r,:d,:by)"),
        {"o": principal.org_id, "b": doc["branch_id"], "t": doc_type, "i": doc_id,
         "a": action, "rep": replaced_by, "r": reason,
         "d": doc[DATE_COL[doc_type]], "by": principal.user_id},
    )
    return {"doc_type": doc_type, "doc_id": doc_id, "status": "cancelled",
            "reversed": {"stock_rows": moved, "party_rows": party, "account_rows": acct},
            "reason": reason}


async def link_revision(
    session: AsyncSession, doc_type: str, old_id: int, new_id: int, revision_no: int
) -> None:
    """Point the two revisions at each other so either can be found from the other."""
    await session.execute(
        text(f"UPDATE {doc_type} SET superseded_by=:n WHERE id=:o"), {"n": new_id, "o": old_id}
    )
    await session.execute(
        text(f"UPDATE {doc_type} SET amended_from=:o, revision_no=:r WHERE id=:n"),
        {"o": old_id, "r": revision_no, "n": new_id},
    )
