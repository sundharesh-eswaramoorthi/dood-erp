from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

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
    PartyUpdate,
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


async def _opening_seq(session: AsyncSession, org_id: int, party_id: int) -> int:
    """Rows already posted for this party's opening balance.

    Used as the next reversal_seq so a corrected opening never collides with
    uq_party_ledger_source. Initial post = seq 0; each edit consumes a new seq.
    """
    return int(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM party_ledger_entry WHERE org_id=:o "
                    "AND source_doc_type='party_opening' AND source_doc_id=:p"
                ),
                {"o": org_id, "p": party_id},
            )
        ).scalar_one()
    )


async def _post_opening(
    session: AsyncSession,
    principal: Principal,
    party: Party,
    amount: Decimal,
    side: str,
    as_of: dt.date,
    *,
    entry_purpose: str = "original",
    reversal_seq: int = 0,
) -> None:
    """A receivable opening is a debit (they owe us); payable is a credit."""
    if amount is None or amount <= 0:
        return
    await post_party_entry(
        session,
        org_id=principal.org_id,
        branch_id=party.serving_branch_id,
        party_id=party.id,
        entry_side="debit" if side == "receivable" else "credit",
        amount=amount,
        source=("party_opening", party.id, 0),
        effective_date=as_of,
        created_by=principal.user_id,
        entry_purpose=entry_purpose,
        reversal_seq=reversal_seq,
    )


async def _require_branch(session: AsyncSession, principal: Principal, branch_id: int) -> None:
    """The branch must exist in the org AND be one this user may work in.

    Checking only the org let anyone file a party against any branch in the
    business, including ones they cannot otherwise see — the branch picker
    offers their own branches, so the server holds them to the same list.
    """
    ok = (
        await session.execute(
            text("SELECT 1 FROM branch WHERE id=:b AND org_id=:o AND is_active"),
            {"b": branch_id, "o": principal.org_id},
        )
    ).scalar_one_or_none()
    if ok is None:
        raise ValueError(f"Branch {branch_id} not found in this organisation")
    if branch_id not in principal.branch_ids:
        raise PermissionError(f"You do not have access to branch {branch_id}")


async def create_party(
    session: AsyncSession, principal: Principal, data: PartyCreate, idem_key: str | None
) -> Party:
    # v2.16: the serving branch IS the visibility boundary — only this branch
    # sees this party. Reversal of the v2 §9 all-branch model, accepted with
    # the cost that a customer buying from two branches needs a record in each.
    branch_id = data.serving_branch_id
    await _require_branch(session, principal, branch_id)

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
        serving_branch_id=branch_id,
        party_code=code,
        name=data.name,
        area=data.area.strip(),
        gstin=data.gstin,
        phone=data.phone,
        pan=data.pan,
        credit_limit=data.credit_limit,
        opening_balance=data.opening_balance,
        opening_balance_side=data.opening_balance_side,
        opening_as_of=data.opening_as_of or dt.date.today(),
        is_active=data.is_active,
        created_by=principal.user_id,
    )
    session.add(party)
    await session.flush()

    # Same transaction as the party itself: a party that exists without the
    # address the operator just typed is worse than no party at all.
    if data.address is not None:
        await add_address(session, principal, party.id, data.address)
    for i, contact in enumerate(data.contacts):
        # first contact is the primary one unless the caller says otherwise
        if i == 0 and not any(c.is_primary for c in data.contacts):
            contact = contact.model_copy(update={"is_primary": True})
        await add_contact(session, principal, party.id, contact)

    await _post_opening(
        session, principal, party,
        data.opening_balance, data.opening_balance_side, party.opening_as_of,
    )

    await emit(
        session,
        principal.org_id,
        "party.created",
        {"party_id": party.id, "code": code, "name": party.name,
         "serving_branch_id": branch_id, "by": principal.user_id},
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


async def update_party(
    session: AsyncSession, principal: Principal, party_id: int, data: PartyUpdate
) -> Party:
    party = await _require_party(session, party_id)
    fields = data.model_dump(exclude_unset=True)

    # moving a party to a branch you cannot work in is the same hole as
    # creating one there
    moved_to = None
    if "serving_branch_id" in fields and fields["serving_branch_id"] is not None:
        await _require_branch(session, principal, fields["serving_branch_id"])
        if fields["serving_branch_id"] != party.serving_branch_id:
            moved_to = fields["serving_branch_id"]

    # Opening balance is ledger-backed: correct it by reversing the old posting
    # and writing a fresh one, never by editing history.
    old_amt, old_side = Decimal(party.opening_balance), party.opening_balance_side
    new_amt = fields.get("opening_balance", old_amt)
    new_side = fields.get("opening_balance_side", old_side)
    new_asof = fields.get("opening_as_of", party.opening_as_of) or dt.date.today()
    opening_changed = (
        new_amt is not None and (Decimal(new_amt) != old_amt or new_side != old_side)
    )

    # gstin/phone/pan/credit_limit are nullable — an explicit null clears them.
    # These are NOT NULL, so a null means "leave alone", not "wipe".
    non_nullable = {
        "name", "area", "is_active",
        "opening_balance", "opening_balance_side", "serving_branch_id",
    }
    for key, value in fields.items():
        if value is None and key in non_nullable:
            continue
        if key == "area":
            value = value.strip()
        setattr(party, key, value)
    if fields.get("opening_as_of") is None and opening_changed:
        party.opening_as_of = new_asof

    if opening_changed:
        seq = await _opening_seq(session, principal.org_id, party.id)
        # reverse the previous figure (opposite side, same amount)
        await _post_opening(
            session, principal, party, old_amt,
            "payable" if old_side == "receivable" else "receivable",
            party.opening_as_of or new_asof,
            entry_purpose="reversal", reversal_seq=seq,
        )
        await _post_opening(
            session, principal, party, Decimal(new_amt), new_side, new_asof,
            entry_purpose="original", reversal_seq=seq,
        )

    await session.flush()

    # Contacts, addresses, documents and GST registrations carry their own
    # branch_id, and branch RLS now reads it. Moving the party without moving
    # them would leave the details behind in a branch that can no longer see
    # the party they belong to — they would simply disappear.
    if moved_to is not None:
        for child in ("party_contact", "party_address", "party_document",
                      "party_gst_registration"):
            await session.execute(
                text(f"UPDATE {child} SET branch_id = :b WHERE party_id = :p"),
                {"b": moved_to, "p": party.id},
            )

    await emit(session, principal.org_id, "party.updated",
               {"party_id": party.id, "fields": sorted(fields), "by": principal.user_id})
    return party


# Whitelisted sort keys -> SQL expressions (never interpolate caller input).
_SORTS = {
    "name": "lower(p.name)",
    "code": "p.party_code",
    "area": "lower(p.area)",
    "created": "p.id",
    "receivable": "COALESCE(pb.receivable, 0)",
    "payable": "COALESCE(pb.payable, 0)",
    "balance": "COALESCE(pb.net_balance, 0)",
}


async def list_parties(
    session: AsyncSession,
    principal: Principal,
    q: str | None = None,
    *,
    area: str | None = None,
    is_active: bool | None = None,
    serving_branch_id: int | None = None,
    tag_id: int | None = None,
    sort: str = "created",
    direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """v2 §1 search / filter / sort, with live outstanding joined in."""
    where = ["TRUE"]
    params: dict = {"o": principal.org_id, "limit": min(limit, 500), "offset": max(offset, 0)}

    if q:
        where.append(
            "(p.name ILIKE :q OR p.party_code ILIKE :q OR p.phone ILIKE :q OR p.area ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    if area:
        where.append("lower(p.area) = lower(:area)")
        params["area"] = area
    if is_active is not None:
        where.append("p.is_active = :active")
        params["active"] = is_active
    if serving_branch_id is not None:
        where.append("p.serving_branch_id = :sb")
        params["sb"] = serving_branch_id
    if tag_id is not None:
        where.append(
            "EXISTS (SELECT 1 FROM tag_assignment ta WHERE ta.entity_type='party' "
            "AND ta.entity_id = p.id AND ta.tag_id = :tag)"
        )
        params["tag"] = tag_id

    order = _SORTS.get(sort, _SORTS["created"])
    order_dir = "ASC" if direction.lower() == "asc" else "DESC"

    rows = (
        await session.execute(
            text(
                "SELECT p.id, p.party_code, p.name, p.area, p.gstin, p.phone, "
                "       p.pan, p.credit_limit, p.opening_balance, p.opening_balance_side, "
                "       p.opening_as_of, p.is_active, p.serving_branch_id, "
                "       COALESCE(pb.net_balance, 0) AS net_balance, "
                "       COALESCE(pb.receivable, 0)  AS receivable, "
                "       COALESCE(pb.payable, 0)     AS payable "
                "FROM party p "
                "LEFT JOIN party_balance pb ON pb.org_id = p.org_id AND pb.party_id = p.id "
                f"WHERE {' AND '.join(where)} "
                f"ORDER BY {order} {order_dir}, p.id DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_areas(session: AsyncSession, principal: Principal) -> list[str]:
    """Distinct areas, for the filter dropdown."""
    rows = (
        await session.execute(
            text("SELECT DISTINCT area FROM party WHERE area <> '' ORDER BY area")
        )
    ).scalars().all()
    return list(rows)


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
        org_id=principal.org_id, branch_id=party.serving_branch_id, party_id=party.id,
        name=data.name, phone=data.phone, email=data.email,
        designation=data.designation, relationship=data.relationship,
        is_primary=data.is_primary,
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
    lat, lng = _geo_from_link(data)
    row = PartyAddress(
        org_id=principal.org_id, branch_id=party.serving_branch_id, party_id=party.id,
        label=data.label, line1=data.line1, line2=data.line2, city=data.city,
        state=data.state, pincode=data.pincode, lat=lat, lng=lng,
        place_id=data.place_id, is_default=data.is_default, map_link=data.map_link,
    )
    session.add(row)
    await session.flush()
    return row


# A Google Maps URL carries the coordinates in one of a few shapes:
#   .../@11.3410,77.7172,15z    ?q=11.3410,77.7172    !3d11.3410!4d77.7172
_GEO_PATTERNS = (
    re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"[?&]q=(-?\d+\.\d+),\s*(-?\d+\.\d+)"),
    re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)"),
)


def _geo_from_link(data: AddressCreate) -> tuple[Decimal | None, Decimal | None]:
    """The address's coordinates, read out of the pasted link if not typed in.

    Short links (maps.app.goo.gl/...) hold no coordinates until they are
    followed, which would mean an outbound request while posting a party — so
    those simply keep the link and no coordinates.
    """
    if data.lat is not None or data.lng is not None or not data.map_link:
        return data.lat, data.lng
    for pattern in _GEO_PATTERNS:
        m = pattern.search(data.map_link)
        if m:
            return Decimal(m.group(1)), Decimal(m.group(2))
    return None, None


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
        org_id=principal.org_id, branch_id=party.serving_branch_id, party_id=party.id,
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
        org_id=principal.org_id, branch_id=party.serving_branch_id, party_id=party.id,
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
            {"o": principal.org_id, "b": party.serving_branch_id, "p": party_id, "no": number,
             "note": data.note, "by": principal.user_id},
        )
    ).scalar_one()
    await post_party_entry(
        session,
        org_id=principal.org_id, branch_id=party.serving_branch_id, party_id=party_id,
        entry_side=data.entry_side, amount=data.amount,
        source=("journal_voucher", jv_id, 0),
        effective_date=data.effective_date or dt.date.today(),
        created_by=principal.user_id, gst_registration_id=data.gst_registration_id,
    )
    await emit(session, principal.org_id, "party.ledger",
               {"party_id": party_id, "side": data.entry_side, "amount": str(data.amount)})
    return await get_ledger(session, principal, party_id)


async def get_ledger(session: AsyncSession, principal: Principal, party_id: int) -> dict:
    party = await _require_party(session, party_id)
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
    receivable = Decimal(bal["receivable"]) if bal else Decimal(0)
    limit = Decimal(party.credit_limit) if party.credit_limit is not None else None
    return {
        "party_id": party_id,
        "opening_balance": party.opening_balance,
        "opening_balance_side": party.opening_balance_side,
        "credit_limit": limit,
        "credit_available": (limit - receivable) if limit is not None else None,
        "net_balance": bal["net_balance"] if bal else 0,
        "receivable": receivable,
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
        "area": party.area,
        "gstin": party.gstin,
        "phone": party.phone,
        "pan": party.pan,
        "credit_limit": party.credit_limit,
        "opening_balance": party.opening_balance,
        "opening_balance_side": party.opening_balance_side,
        "opening_as_of": party.opening_as_of,
        "is_active": party.is_active,
        "serving_branch_id": party.serving_branch_id,
        "contacts": await list_contacts(session, party_id),
        "addresses": await list_addresses(session, party_id),
        "gst_registrations": await list_gst(session, party_id),
        "documents": await list_documents(session, party_id),
        "tags": await list_party_tags(session, party_id),
    }
