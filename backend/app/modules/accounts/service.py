"""Bank/cash accounts + payment vouchers.

A receipt (customer pays us): party CREDIT (reduces receivable) + account IN.
A payment (we pay a supplier): party DEBIT (reduces payable) + account OUT.
Both legs commit in one transaction.

v2 §3 adds the third leg: the settlement is allocated against specific bills
(app.services.allocation), which is what makes "payment history" on an invoice
and bill-wise outstanding possible at all.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.party import Party
from app.modules.accounts.schemas import (
    AccountCreate,
    ExpenseCategoryCreate,
    ExpenseCreate,
    VoucherCreate,
)
from app.services import allocation as alloc
from app.services.account_ledger import post_account_entry
from app.services.numbering import allocate
from app.services.outbox import emit
from app.services.party_ledger import post_entry as post_party_entry


async def list_accounts(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, name, account_type, current_balance, branch_id "
                 "FROM cash_bank_account WHERE is_active ORDER BY name")
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_account(session: AsyncSession, principal: Principal, data: AccountCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError(f"You do not have access to branch {branch_id}")
    try:
        row = (
            await session.execute(
                text("INSERT INTO cash_bank_account (org_id, branch_id, name, account_type, "
                     "opening_balance, current_balance) "
                     "VALUES (:o,:b,:n,:t,:ob,:ob) "
                     "RETURNING id, name, account_type, current_balance, branch_id"),
                {"o": principal.org_id, "b": branch_id, "n": data.name,
                 "t": data.account_type, "ob": data.opening_balance},
            )
        ).mappings().one()
    except IntegrityError as e:
        raise ValueError(f"Account '{data.name}' already exists") from e
    return dict(row)


async def post_voucher(session: AsyncSession, principal: Principal, data: VoucherCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    party = (await session.execute(select(Party).where(Party.id == data.party_id))).scalar_one_or_none()
    if party is None:
        raise ValueError("party not found")

    # Check every tender before writing anything: the voucher header carries the
    # first split's account, so a bad id would otherwise surface as a raw
    # foreign-key 500 from the INSERT below rather than a 422 naming it.
    splits = data.settlement()
    for split in splits:
        ok = (
            await session.execute(
                text("SELECT 1 FROM cash_bank_account WHERE id=:a AND org_id=:o AND is_active"),
                {"a": split.account_id, "o": principal.org_id},
            )
        ).scalar_one_or_none()
        if ok is None:
            raise ValueError(f"payment account {split.account_id} not found")
        if split.payment_type_id is not None:
            ok = (
                await session.execute(
                    text("SELECT 1 FROM payment_type WHERE id=:p AND org_id=:o AND is_active"),
                    {"p": split.payment_type_id, "o": principal.org_id},
                )
            ).scalar_one_or_none()
            if ok is None:
                raise ValueError(f"payment type {split.payment_type_id} not found")

    vdate = data.voucher_date or dt.date.today()
    number = await allocate(session, principal.org_id, None, "payment_voucher")
    vid = (
        await session.execute(
            text("INSERT INTO payment_voucher (org_id, branch_id, party_id, account_id, doc_no, voucher_type, "
                 "amount, voucher_date, note, payment_type_id, created_by) "
                 "VALUES (:o,:b,:p,:a,:no,:vt,:amt,:vd,:nt,:pt,:by) RETURNING id"),
            {"o": principal.org_id, "b": branch_id, "p": data.party_id, "a": data.account_id, "no": number,
             "vt": data.voucher_type, "amt": data.amount, "vd": vdate, "nt": data.note,
             "pt": data.payment_type_id, "by": principal.user_id},
        )
    ).scalar_one()

    if data.voucher_type == "receipt":
        party_side, acct_dir = "credit", "in"
    else:  # payment
        party_side, acct_dir = "debit", "out"

    settle_entry_id, party_net = await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.party_id,
        entry_side=party_side, amount=data.amount, source=("payment_voucher", vid, 0),
        effective_date=vdate, created_by=principal.user_id,
    )
    # v2 §3 split payment: the party sees one receipt, but the cash may have
    # arrived through several accounts, so each tender gets its own account
    # entry (seq = source_line_no) and its own document_payment row.
    acct_bal = Decimal(0)
    for seq, split in enumerate(splits):
        acct_bal = await post_account_entry(
            session, org_id=principal.org_id, account_id=split.account_id, direction=acct_dir,
            amount=split.amount, source=("payment_voucher", vid, seq),
            effective_date=vdate, created_by=principal.user_id,
        )
        await session.execute(
            text(
                "INSERT INTO document_payment "
                "(org_id, branch_id, doc_type, doc_id, seq, account_id, payment_type_id, "
                " amount, reference) "
                "VALUES (:o,:b,'payment_voucher',:di,:s,:a,:pt,:amt,:ref)"
            ),
            {"o": principal.org_id, "b": branch_id, "di": vid, "s": seq,
             "a": split.account_id, "pt": split.payment_type_id, "amt": split.amount,
             "ref": split.reference},
        )
    # v2 §3 payment history — say which bills this settles.
    #   allocations given  -> exactly those
    #   allocations omitted-> oldest open items first (the usual counter behaviour)
    #   allocations == []  -> leave it on account, unallocated
    if data.allocations is None:
        made = await alloc.auto_allocate(session, principal.org_id, settle_entry_id=settle_entry_id)
    else:
        made = await alloc.allocate(
            session, principal.org_id, settle_entry_id=settle_entry_id,
            targets=[(a.against_entry_id, a.amount) for a in data.allocations],
        )
    applied = sum((m["amount"] for m in made), Decimal(0))

    await emit(session, principal.org_id, "payment",
               {"voucher_id": vid, "type": data.voucher_type, "amount": str(data.amount),
                "allocated": str(applied)})
    return {"id": vid, "doc_no": number, "voucher_type": data.voucher_type, "party_id": data.party_id,
            "account_id": data.account_id, "amount": data.amount, "account_balance": acct_bal,
            "party_net": party_net, "payment_type_id": data.payment_type_id,
            "payments": [
                {"seq": i, "account_id": s.account_id, "payment_type_id": s.payment_type_id,
                 "amount": s.amount, "reference": s.reference}
                for i, s in enumerate(splits)
            ],
            "allocations": made, "unallocated": Decimal(data.amount) - applied}


# ---- payment types (v2 §3 "add payment type") ----
PT_COLS = "id, name, kind, default_account_id, is_active, sort_order"


async def list_payment_types(
    session: AsyncSession, principal: Principal, include_inactive: bool = False
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                f"SELECT {PT_COLS} FROM payment_type WHERE org_id=:o "
                f"{'' if include_inactive else 'AND is_active '}ORDER BY sort_order, name"
            ),
            {"o": principal.org_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_payment_type(session: AsyncSession, principal: Principal, data) -> dict:
    try:
        row = (
            await session.execute(
                text("INSERT INTO payment_type (org_id, name, kind, default_account_id, sort_order) "
                     f"VALUES (:o,:n,:k,:a,:s) RETURNING {PT_COLS}"),
                {"o": principal.org_id, "n": data.name, "k": data.kind,
                 "a": data.default_account_id, "s": data.sort_order},
            )
        ).mappings().one()
    except IntegrityError as e:
        raise ValueError(f"Payment type '{data.name}' already exists") from e
    return dict(row)


async def update_payment_type(
    session: AsyncSession, principal: Principal, pt_id: int, data
) -> dict:
    fields = data.model_dump(exclude_unset=True)
    non_nullable = {"name", "kind", "is_active", "sort_order"}
    sets, params = [], {}
    for i, (k, v) in enumerate(fields.items()):
        if v is None and k in non_nullable:
            continue
        sets.append(f"{k} = :v{i}")
        params[f"v{i}"] = v
    if not sets:
        raise ValueError("nothing to update")
    params |= {"i": pt_id, "o": principal.org_id}
    row = (
        await session.execute(
            text(f"UPDATE payment_type SET {', '.join(sets)} WHERE id=:i AND org_id=:o RETURNING {PT_COLS}"),
            params,
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Payment type not found")
    return dict(row)


# ---- open items / allocation views ----
async def party_open_items(
    session: AsyncSession, principal: Principal, party_id: int, side: str = "debit"
) -> list[dict]:
    """What this party still owes, bill by bill (or what we owe them)."""
    return await alloc.open_items(session, principal.org_id, party_id, side)


async def allocate_voucher(
    session: AsyncSession, principal: Principal, voucher_id: int, allocations
) -> dict:
    """Apply an already-posted receipt/payment to specific bills."""
    entry_id = (
        await session.execute(
            text("SELECT id FROM party_ledger_entry WHERE org_id=:o "
                 "AND source_doc_type='payment_voucher' AND source_doc_id=:v ORDER BY id LIMIT 1"),
            {"o": principal.org_id, "v": voucher_id},
        )
    ).scalar_one_or_none()
    if entry_id is None:
        raise LookupError("Payment voucher not found")
    made = (
        await alloc.auto_allocate(session, principal.org_id, settle_entry_id=entry_id)
        if not allocations
        else await alloc.allocate(
            session, principal.org_id, settle_entry_id=entry_id,
            targets=[(a.against_entry_id, a.amount) for a in allocations],
        )
    )
    free = Decimal(
        (await session.execute(
            text("SELECT amount FROM party_ledger_entry WHERE id=:i"), {"i": entry_id}
        )).scalar_one()
    ) - await alloc.allocated_as_settle(session, principal.org_id, entry_id)
    return {"voucher_id": voucher_id, "allocations": made, "unallocated": free}


async def list_vouchers(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, doc_no, voucher_type, party_id, account_id, amount, voucher_date "
                 "FROM payment_voucher ORDER BY id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ---- expenses ----
async def list_expense_categories(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (await session.execute(text("SELECT id, name FROM expense_category WHERE is_active ORDER BY name"))).mappings().all()
    return [dict(r) for r in rows]


async def create_expense_category(session: AsyncSession, principal: Principal, data: ExpenseCategoryCreate) -> dict:
    try:
        row = (
            await session.execute(
                text("INSERT INTO expense_category (org_id, name) VALUES (:o,:n) RETURNING id, name"),
                {"o": principal.org_id, "n": data.name},
            )
        ).mappings().one()
    except IntegrityError as e:
        raise ValueError(f"Category '{data.name}' already exists") from e
    return dict(row)


async def post_expense(session: AsyncSession, principal: Principal, data: ExpenseCreate) -> dict:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted")
    acct = (await session.execute(text("SELECT id FROM cash_bank_account WHERE id=:a"), {"a": data.account_id})).scalar_one_or_none()
    if acct is None:
        raise ValueError("account not found")

    edate = data.expense_date or dt.date.today()
    number = await allocate(session, principal.org_id, None, "expense")
    exp_id = (
        await session.execute(
            text("INSERT INTO expense (org_id, branch_id, account_id, category_id, doc_no, amount, expense_date, note, created_by) "
                 "VALUES (:o,:b,:a,:c,:no,:amt,:ed,:nt,:by) RETURNING id"),
            {"o": principal.org_id, "b": branch_id, "a": data.account_id, "c": data.category_id, "no": number,
             "amt": data.amount, "ed": edate, "nt": data.note, "by": principal.user_id},
        )
    ).scalar_one()
    # money leaves the account
    acct_bal = await post_account_entry(
        session, org_id=principal.org_id, account_id=data.account_id, direction="out",
        amount=data.amount, source=("expense", exp_id, 0), effective_date=edate, created_by=principal.user_id,
    )
    await emit(session, principal.org_id, "expense", {"expense_id": exp_id, "amount": str(data.amount)})
    return {"id": exp_id, "doc_no": number, "amount": data.amount, "account_id": data.account_id,
            "category_id": data.category_id, "account_balance": acct_bal}


async def list_expenses(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT e.id, e.doc_no, e.amount, e.account_id, e.category_id, e.expense_date, e.note, c.name AS category "
                 "FROM expense e LEFT JOIN expense_category c ON c.id=e.category_id ORDER BY e.id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
