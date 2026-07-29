from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.party import (
    Party,
    PartyAddress,
    PartyContact,
    PartyDocument,
    PartyGstRegistration,
)
from app.modules.parties.schemas import (
    AddressCreate,
    ContactCreate,
    DocumentCreate,
    GstRegCreate,
    LedgerEntryCreate,
    PartyCreate,
)
from app.services.numbering import allocate
from app.services.outbox import emit
from app.services.party_ledger import post_entry as post_party_entry


async def get_party(session: AsyncSession, party_id: int) -> Party | None:
    return (
        await session.execute(select(Party).where(Party.id == party_id))
    ).scalar_one_or_none()


async def _require_party(session: AsyncSession, party_id: int) -> Party:
    party = await get_party(session, party_id)
    if party is None:
        raise LookupError("Party not found")
    return party


async def create_party(
    session: AsyncSession, principal: Principal, data: PartyCreate, idem_key: str | None
) -> Party:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted for this user")

    if idem_key:
        existing = (
            await session.execute(
                text("SELECT response_doc_id FROM idempotency_key WHERE org_id = :o AND key = :k"),
                {"o": principal.org_id, "k": idem_key},
            )
        ).scalar()
        if existing:
            party = await get_party(session, int(existing))
            if party is not None:
                return party

    code = await allocate(session, principal.org_id, None, "party")
    party = Party(
        org_id=principal.org_id,
        branch_id=branch_id,
        party_code=code,
        name=data.name,
        party_type=data.party_type,
        gstin=data.gstin,
        phone=data.phone,
        pan=data.pan,
        credit_limit=data.credit_limit,
        created_by=principal.user_id,
    )
    session.add(party)
    await session.flush()

    await emit(
        session,
        principal.org_id,
        "party.created",
        {"party_id": party.id, "code": code, "name": party.name, "branch_id": branch_id,
         "by": principal.user_id},
    )
    if idem_key:
        await session.execute(
            text(
                "INSERT INTO idempotency_key (org_id, key, request_hash, response_doc_type, response_doc_id) "
                "VALUES (:o, :k, '', 'party', :id) ON CONFLICT DO NOTHING"
            ),
            {"o": principal.org_id, "k": idem_key, "id": party.id},
        )
    return party


async def list_parties(
    session: AsyncSession, principal: Principal, q: str | None = None, limit: int = 50
) -> list[Party]:
    stmt = select(Party).order_by(Party.id.desc()).limit(limit)
    if q:
        stmt = stmt.where(Party.name.ilike(f"%{q}%"))
    return list((await session.execute(stmt)).scalars().all())


# ---- sub-resources ----
async def list_contacts(session: AsyncSession, party_id: int) -> list[PartyContact]:
    return list(
        (await session.execute(select(PartyContact).where(PartyContact.party_id == party_id))).scalars().all()
    )


async def add_contact(
    session: AsyncSession, principal: Principal, party_id: int, data: ContactCreate
) -> PartyContact:
    party = await _require_party(session, party_id)
    row = PartyContact(
        org_id=principal.org_id, branch_id=party.branch_id, party_id=party.id,
        name=data.name, phone=data.phone, email=data.email,
        designation=data.designation, is_primary=data.is_primary,
    )
    session.add(row)
    await session.flush()
    return row


async def list_addresses(session: AsyncSession, party_id: int) -> list[PartyAddress]:
    return list(
        (await session.execute(select(PartyAddress).where(PartyAddress.party_id == party_id))).scalars().all()
    )


async def add_address(
    session: AsyncSession, principal: Principal, party_id: int, data: AddressCreate
) -> PartyAddress:
    party = await _require_party(session, party_id)
    row = PartyAddress(
        org_id=principal.org_id, branch_id=party.branch_id, party_id=party.id,
        label=data.label, line1=data.line1, line2=data.line2, city=data.city,
        state=data.state, pincode=data.pincode, lat=data.lat, lng=data.lng,
        place_id=data.place_id, is_default=data.is_default,
    )
    session.add(row)
    await session.flush()
    return row


async def list_gst(session: AsyncSession, party_id: int) -> list[PartyGstRegistration]:
    return list(
        (await session.execute(
            select(PartyGstRegistration).where(PartyGstRegistration.party_id == party_id)
        )).scalars().all()
    )


async def add_gst(
    session: AsyncSession, principal: Principal, party_id: int, data: GstRegCreate
) -> PartyGstRegistration:
    party = await _require_party(session, party_id)
    row = PartyGstRegistration(
        org_id=principal.org_id, branch_id=party.branch_id, party_id=party.id,
        gstin=data.gstin.upper(), state_code=data.state_code or data.gstin[:2],
        legal_name=data.legal_name, is_default=data.is_default,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError(f"GSTIN '{data.gstin}' is already registered") from e
    return row


async def list_documents(session: AsyncSession, party_id: int) -> list[PartyDocument]:
    return list(
        (await session.execute(select(PartyDocument).where(PartyDocument.party_id == party_id))).scalars().all()
    )


async def add_document(
    session: AsyncSession, principal: Principal, party_id: int, data: DocumentCreate
) -> PartyDocument:
    party = await _require_party(session, party_id)
    row = PartyDocument(
        org_id=principal.org_id, branch_id=party.branch_id, party_id=party.id,
        doc_type=data.doc_type, file_name=data.file_name, storage_key=data.storage_key,
        content_type=data.content_type, uploaded_by=principal.user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def post_manual_ledger(
    session: AsyncSession, principal: Principal, party_id: int, data: LedgerEntryCreate
) -> dict:
    party = await _require_party(session, party_id)
    number = await allocate(session, principal.org_id, None, "journal")
    jv_id = (
        await session.execute(
            text(
                "INSERT INTO journal_voucher (org_id, branch_id, party_id, doc_no, note, created_by) "
                "VALUES (:o, :b, :p, :no, :note, :by) RETURNING id"
            ),
            {"o": principal.org_id, "b": party.branch_id, "p": party_id, "no": number,
             "note": data.note, "by": principal.user_id},
        )
    ).scalar_one()
    await post_party_entry(
        session,
        org_id=principal.org_id, branch_id=party.branch_id, party_id=party_id,
        entry_side=data.entry_side, amount=data.amount,
        source=("journal_voucher", jv_id, 0),
        effective_date=data.effective_date or dt.date.today(),
        created_by=principal.user_id, gst_registration_id=data.gst_registration_id,
    )
    await emit(session, principal.org_id, "party.ledger",
               {"party_id": party_id, "side": data.entry_side, "amount": str(data.amount)})
    return await get_ledger(session, principal, party_id)


async def get_ledger(session: AsyncSession, principal: Principal, party_id: int) -> dict:
    await _require_party(session, party_id)
    bal = (
        await session.execute(
            text("SELECT net_balance, receivable, payable FROM party_balance WHERE org_id=:o AND party_id=:p"),
            {"o": principal.org_id, "p": party_id},
        )
    ).mappings().first()
    entries = (
        await session.execute(
            text(
                "SELECT id, entry_side, amount, source_doc_type, source_doc_id, effective_date "
                "FROM party_ledger_entry WHERE org_id=:o AND party_id=:p ORDER BY id DESC LIMIT 100"
            ),
            {"o": principal.org_id, "p": party_id},
        )
    ).mappings().all()
    return {
        "party_id": party_id,
        "net_balance": bal["net_balance"] if bal else 0,
        "receivable": bal["receivable"] if bal else 0,
        "payable": bal["payable"] if bal else 0,
        "entries": [dict(e) for e in entries],
    }


async def list_party_tags(session: AsyncSession, party_id: int) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT td.id, td.name, td.color FROM tag_assignment ta "
                "JOIN tag_definition td ON td.id = ta.tag_id "
                "WHERE ta.entity_type='party' AND ta.entity_id=:p ORDER BY td.name"
            ),
            {"p": party_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def add_tag(session: AsyncSession, principal: Principal, party_id: int, tag_id: int) -> list[dict]:
    await _require_party(session, party_id)  # 404 if not visible
    await session.execute(
        text(
            "INSERT INTO tag_assignment (org_id, tag_id, entity_type, entity_id) "
            "VALUES (:o, :t, 'party', :p) ON CONFLICT DO NOTHING"
        ),
        {"o": principal.org_id, "t": tag_id, "p": party_id},
    )
    return await list_party_tags(session, party_id)


async def remove_tag(session: AsyncSession, principal: Principal, party_id: int, tag_id: int) -> list[dict]:
    await _require_party(session, party_id)
    await session.execute(
        text(
            "DELETE FROM tag_assignment WHERE org_id=:o AND tag_id=:t "
            "AND entity_type='party' AND entity_id=:p"
        ),
        {"o": principal.org_id, "t": tag_id, "p": party_id},
    )
    return await list_party_tags(session, party_id)


async def get_party_detail(session: AsyncSession, party_id: int) -> dict:
    party = await _require_party(session, party_id)
    return {
        "id": party.id,
        "party_code": party.party_code,
        "name": party.name,
        "party_type": party.party_type,
        "gstin": party.gstin,
        "phone": party.phone,
        "pan": party.pan,
        "credit_limit": party.credit_limit,
        "branch_id": party.branch_id,
        "contacts": await list_contacts(session, party_id),
        "addresses": await list_addresses(session, party_id),
        "gst_registrations": await list_gst(session, party_id),
        "documents": await list_documents(session, party_id),
        "tags": await list_party_tags(session, party_id),
    }
