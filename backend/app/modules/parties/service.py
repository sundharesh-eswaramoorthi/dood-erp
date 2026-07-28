from __future__ import annotations

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
    PartyCreate,
)
from app.services.numbering import allocate
from app.services.outbox import emit


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
    }
