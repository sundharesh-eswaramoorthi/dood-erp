from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.party import Party
from app.modules.parties.schemas import PartyCreate
from app.services.numbering import allocate
from app.services.outbox import emit


async def get_party(session: AsyncSession, party_id: int) -> Party | None:
    return (
        await session.execute(select(Party).where(Party.id == party_id))
    ).scalar_one_or_none()


async def create_party(
    session: AsyncSession,
    principal: Principal,
    data: PartyCreate,
    idem_key: str | None,
) -> Party:
    branch_id = data.branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if branch_id is None:
        raise ValueError("Caller has no branch access")
    if branch_id not in principal.branch_ids:
        raise PermissionError("Branch not permitted for this user")

    # Idempotency: replay returns the original result.
    if idem_key:
        existing = (
            await session.execute(
                text(
                    "SELECT response_doc_id FROM idempotency_key WHERE org_id = :o AND key = :k"
                ),
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
        created_by=principal.user_id,
    )
    session.add(party)
    await session.flush()  # assigns party.id

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
    session: AsyncSession,
    principal: Principal,
    q: str | None = None,
    limit: int = 50,
) -> list[Party]:
    # RLS scopes rows to the caller's org + branches automatically.
    stmt = select(Party).order_by(Party.id.desc()).limit(limit)
    if q:
        stmt = stmt.where(Party.name.ilike(f"%{q}%"))
    return list((await session.execute(stmt)).scalars().all())
