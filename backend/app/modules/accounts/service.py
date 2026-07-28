"""Bank/cash accounts + payment vouchers.

A receipt (customer pays us): party CREDIT (reduces receivable) + account IN.
A payment (we pay a supplier): party DEBIT (reduces payable) + account OUT.
Both legs commit in one transaction.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.party import Party
from app.modules.accounts.schemas import AccountCreate, VoucherCreate
from app.services.account_ledger import post_account_entry
from app.services.numbering import allocate
from app.services.outbox import emit
from app.services.party_ledger import post_entry as post_party_entry


async def list_accounts(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, name, account_type, current_balance FROM cash_bank_account "
                 "WHERE is_active ORDER BY name")
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_account(session: AsyncSession, principal: Principal, data: AccountCreate) -> dict:
    try:
        row = (
            await session.execute(
                text("INSERT INTO cash_bank_account (org_id, name, account_type, opening_balance, current_balance) "
                     "VALUES (:o,:n,:t,:ob,:ob) RETURNING id, name, account_type, current_balance"),
                {"o": principal.org_id, "n": data.name, "t": data.account_type, "ob": data.opening_balance},
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
    acct = (
        await session.execute(text("SELECT id FROM cash_bank_account WHERE id=:a"), {"a": data.account_id})
    ).scalar_one_or_none()
    if acct is None:
        raise ValueError("account not found")

    vdate = data.voucher_date or dt.date.today()
    number = await allocate(session, principal.org_id, None, "payment_voucher")
    vid = (
        await session.execute(
            text("INSERT INTO payment_voucher (org_id, branch_id, party_id, account_id, doc_no, voucher_type, "
                 "amount, voucher_date, note, created_by) VALUES (:o,:b,:p,:a,:no,:vt,:amt,:vd,:nt,:by) RETURNING id"),
            {"o": principal.org_id, "b": branch_id, "p": data.party_id, "a": data.account_id, "no": number,
             "vt": data.voucher_type, "amt": data.amount, "vd": vdate, "nt": data.note, "by": principal.user_id},
        )
    ).scalar_one()

    if data.voucher_type == "receipt":
        party_side, acct_dir = "credit", "in"
    else:  # payment
        party_side, acct_dir = "debit", "out"

    party_net = await post_party_entry(
        session, org_id=principal.org_id, branch_id=branch_id, party_id=data.party_id,
        entry_side=party_side, amount=data.amount, source=("payment_voucher", vid, 0),
        effective_date=vdate, created_by=principal.user_id,
    )
    acct_bal = await post_account_entry(
        session, org_id=principal.org_id, account_id=data.account_id, direction=acct_dir,
        amount=data.amount, source=("payment_voucher", vid, 0), effective_date=vdate, created_by=principal.user_id,
    )
    await emit(session, principal.org_id, "payment",
               {"voucher_id": vid, "type": data.voucher_type, "amount": str(data.amount)})
    return {"id": vid, "doc_no": number, "voucher_type": data.voucher_type, "party_id": data.party_id,
            "account_id": data.account_id, "amount": data.amount, "account_balance": acct_bal, "party_net": party_net}


async def list_vouchers(session: AsyncSession, principal: Principal, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, doc_no, voucher_type, party_id, account_id, amount, voucher_date "
                 "FROM payment_voucher ORDER BY id DESC LIMIT :l"),
            {"l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
