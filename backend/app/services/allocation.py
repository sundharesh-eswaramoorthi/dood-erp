"""Bill-wise settlement (v2 §3 "Payment history").

party_balance answers "how much does this party owe". It cannot answer "against
which bills", which is what a customer actually argues about and what ageing
reports need. ledger_allocation closes that gap: each row says "this much of
settling entry S paid off outstanding entry A".

Sign convention follows the party ledger:
  customer — the invoice is a DEBIT, the receipt a CREDIT
  supplier — the bill is a CREDIT, the payment a DEBIT
So a settlement always allocates against entries of the OPPOSITE side, and this
module refuses anything else rather than quietly producing a nonsense figure.

Nothing here mutates the ledger; allocations are their own rows, so the
append-only guarantee and the net-balance invariant are untouched.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ZERO = Decimal("0")


class AllocationError(ValueError):
    """The requested settlement doesn't fit the entries it names."""


async def _entry(session: AsyncSession, org_id: int, entry_id: int) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT id, party_id, entry_side, amount, source_doc_type, source_doc_id, "
                "effective_date FROM party_ledger_entry WHERE org_id=:o AND id=:i"
            ),
            {"o": org_id, "i": entry_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AllocationError(f"ledger entry {entry_id} not found")
    return dict(row)


async def allocated_as_settle(session: AsyncSession, org_id: int, entry_id: int) -> Decimal:
    """How much of a settling entry has already been applied to something."""
    return Decimal(
        (await session.execute(
            text("SELECT COALESCE(SUM(amount),0) FROM ledger_allocation "
                 "WHERE org_id=:o AND settle_entry_id=:i"),
            {"o": org_id, "i": entry_id},
        )).scalar_one()
    )


async def allocated_against(session: AsyncSession, org_id: int, entry_id: int) -> Decimal:
    """How much of an outstanding entry has been settled."""
    return Decimal(
        (await session.execute(
            text("SELECT COALESCE(SUM(amount),0) FROM ledger_allocation "
                 "WHERE org_id=:o AND against_entry_id=:i"),
            {"o": org_id, "i": entry_id},
        )).scalar_one()
    )


async def open_items(
    session: AsyncSession, org_id: int, party_id: int, side: str
) -> list[dict]:
    """Entries of `side` that still have something outstanding, oldest first.

    'debit' lists what a customer still owes us; 'credit' what we still owe a
    supplier. Payments themselves are excluded — a receipt is a settlement, not
    an open item.
    """
    rows = (
        await session.execute(
            text(
                "SELECT e.id AS entry_id, e.source_doc_type, e.source_doc_id, e.effective_date, "
                "       e.amount, COALESCE(a.settled, 0) AS settled, "
                "       e.amount - COALESCE(a.settled, 0) AS outstanding "
                "FROM party_ledger_entry e "
                "LEFT JOIN (SELECT against_entry_id, SUM(amount) AS settled "
                "           FROM ledger_allocation WHERE org_id=:o GROUP BY against_entry_id) a "
                "  ON a.against_entry_id = e.id "
                "WHERE e.org_id=:o AND e.party_id=:p AND e.entry_side=:side "
                "  AND e.entry_purpose='original' "
                "  AND e.source_doc_type NOT LIKE '%_payment' "
                "  AND e.source_doc_type <> 'payment_voucher' "
                # A corrected figure leaves the superseded original in place
                # (the ledger is append-only); it must not still read as owed.
                "  AND NOT EXISTS (SELECT 1 FROM party_ledger_entry r "
                "                  WHERE r.org_id = e.org_id "
                "                    AND r.source_doc_type = e.source_doc_type "
                "                    AND r.source_doc_id = e.source_doc_id "
                "                    AND r.source_line_no = e.source_line_no "
                "                    AND r.entry_purpose = 'reversal' "
                "                    AND r.reversal_seq > e.reversal_seq) "
                "  AND e.amount - COALESCE(a.settled, 0) > 0 "
                "ORDER BY e.effective_date, e.id"
            ),
            {"o": org_id, "p": party_id, "side": side},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def allocate(
    session: AsyncSession,
    org_id: int,
    *,
    settle_entry_id: int,
    targets: list[tuple[int, Decimal]],
) -> list[dict]:
    """Apply a settling entry to specific outstanding entries."""
    settle = await _entry(session, org_id, settle_entry_id)
    free = Decimal(settle["amount"]) - await allocated_as_settle(session, org_id, settle_entry_id)

    made = []
    for against_id, amount in targets:
        amount = Decimal(amount)
        if amount <= 0:
            continue
        against = await _entry(session, org_id, against_id)

        if against["party_id"] != settle["party_id"]:
            raise AllocationError("cannot settle one party's entry with another party's payment")
        if against["entry_side"] == settle["entry_side"]:
            raise AllocationError(
                f"a {settle['entry_side']} can only settle a "
                f"{'credit' if settle['entry_side'] == 'debit' else 'debit'}"
            )
        if amount > free:
            raise AllocationError(
                f"only {free} of this payment is unallocated, cannot apply {amount}"
            )
        open_amt = Decimal(against["amount"]) - await allocated_against(session, org_id, against_id)
        if amount > open_amt:
            raise AllocationError(
                f"{against['source_doc_type']} #{against['source_doc_id']} has only "
                f"{open_amt} outstanding, cannot apply {amount}"
            )

        await session.execute(
            text(
                "INSERT INTO ledger_allocation (org_id, party_id, settle_entry_id, "
                "against_entry_id, amount) VALUES (:o,:p,:s,:a,:amt)"
            ),
            {"o": org_id, "p": settle["party_id"], "s": settle_entry_id,
             "a": against_id, "amt": amount},
        )
        free -= amount
        made.append({"against_entry_id": against_id, "amount": amount,
                     "doc_type": against["source_doc_type"], "doc_id": against["source_doc_id"]})
    return made


async def auto_allocate(
    session: AsyncSession, org_id: int, *, settle_entry_id: int
) -> list[dict]:
    """Apply whatever is unallocated on a settling entry to the party's oldest
    open items first — the default behaviour when nobody says otherwise."""
    settle = await _entry(session, org_id, settle_entry_id)
    free = Decimal(settle["amount"]) - await allocated_as_settle(session, org_id, settle_entry_id)
    if free <= 0:
        return []

    opposite = "debit" if settle["entry_side"] == "credit" else "credit"
    targets: list[tuple[int, Decimal]] = []
    for item in await open_items(session, org_id, settle["party_id"], opposite):
        if free <= 0:
            break
        take = min(free, Decimal(item["outstanding"]))
        targets.append((item["entry_id"], take))
        free -= take
    return await allocate(session, org_id, settle_entry_id=settle_entry_id, targets=targets)


async def settle_own_document(
    session: AsyncSession, org_id: int, doc_type: str, doc_id: int
) -> list[dict]:
    """Money taken at the moment an invoice is raised belongs to THAT invoice.

    Auto-FIFO would put it against the oldest open bill instead, which is
    surprising when the customer has just handed over cash for this one.
    """
    # Walk every settling entry rather than assuming there is one. A document
    # amended twice, or one whose payment was re-posted, has more than a single
    # candidate, and `ORDER BY id LIMIT 1` silently left the rest unallocated —
    # the invoice then read as outstanding while the money was already in.
    settle_ids = (
        await session.execute(
            text("SELECT id FROM party_ledger_entry WHERE org_id=:o AND source_doc_type=:t "
                 "AND source_doc_id=:i AND entry_purpose='original' ORDER BY id"),
            {"o": org_id, "t": f"{doc_type}_payment", "i": doc_id},
        )
    ).scalars().all()
    against_id = (
        await session.execute(
            text("SELECT id FROM party_ledger_entry WHERE org_id=:o AND source_doc_type=:t "
                 "AND source_doc_id=:i AND entry_purpose='original' ORDER BY id LIMIT 1"),
            {"o": org_id, "t": doc_type, "i": doc_id},
        )
    ).scalar_one_or_none()
    if not settle_ids or against_id is None:
        return []

    done: list[dict] = []
    for settle_id in settle_ids:
        settle = await _entry(session, org_id, settle_id)
        free = Decimal(settle["amount"]) - await allocated_as_settle(session, org_id, settle_id)
        if free <= 0:
            continue
        # never allocate past what the invoice still owes — the last tender of
        # an overpayment stays on account rather than over-settling the bill
        outstanding = Decimal(
            (await _entry(session, org_id, against_id))["amount"]
        ) - await allocated_against(session, org_id, against_id)
        if outstanding <= 0:
            break
        done += await allocate(
            session, org_id, settle_entry_id=settle_id,
            targets=[(against_id, min(free, outstanding))],
        )
    return done


async def document_payments(
    session: AsyncSession, org_id: int, doc_type: str, doc_id: int
) -> dict:
    """v2 §3 payment history: everything that has settled this document."""
    entry = (
        await session.execute(
            text("SELECT id, amount FROM party_ledger_entry WHERE org_id=:o "
                 "AND source_doc_type=:t AND source_doc_id=:i AND entry_purpose='original' "
                 "ORDER BY id LIMIT 1"),
            {"o": org_id, "t": doc_type, "i": doc_id},
        )
    ).mappings().one_or_none()
    if entry is None:
        return {"invoice_total": ZERO, "settled": ZERO, "outstanding": ZERO, "payments": []}

    rows = (
        await session.execute(
            text(
                "SELECT al.amount, al.created_at, se.source_doc_type, se.source_doc_id, "
                "       se.effective_date, pv.doc_no, pv.voucher_type, "
                # A split settles as ONE party entry, so the tender breakdown
                # lives in document_payment: without this the history could only
                # ever name one mode for money taken three ways.
                "       COALESCE(tender.modes, pt.name) AS payment_type "
                "FROM ledger_allocation al "
                "JOIN party_ledger_entry se ON se.id = al.settle_entry_id "
                "LEFT JOIN payment_voucher pv ON se.source_doc_type='payment_voucher' "
                "     AND pv.id = se.source_doc_id "
                "LEFT JOIN payment_type pt ON pt.id = pv.payment_type_id "
                "LEFT JOIN LATERAL ("
                "   SELECT string_agg(COALESCE(pt2.name, 'Payment'), ', ' ORDER BY dp.seq) AS modes "
                "   FROM document_payment dp "
                "   LEFT JOIN payment_type pt2 ON pt2.id = dp.payment_type_id "
                "   WHERE dp.org_id = al.org_id "
                "     AND dp.doc_type = regexp_replace(se.source_doc_type, '_payment$', '') "
                "     AND dp.doc_id = se.source_doc_id "
                ") tender ON TRUE "
                "WHERE al.org_id=:o AND al.against_entry_id=:e "
                "ORDER BY se.effective_date, al.id"
            ),
            {"o": org_id, "e": entry["id"]},
        )
    ).mappings().all()

    settled = await allocated_against(session, org_id, entry["id"])
    # decimal strings, like every other money field in the API
    return {
        "invoice_total": str(Decimal(entry["amount"])),
        "settled": str(settled),
        "outstanding": str(Decimal(entry["amount"]) - settled),
        "payments": [
            {**dict(r), "amount": str(r["amount"])} for r in rows
        ],
    }
