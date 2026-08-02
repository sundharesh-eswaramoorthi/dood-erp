from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.parties import service
from app.modules.parties.schemas import (
    AddressCreate,
    AddressOut,
    ContactCreate,
    ContactOut,
    DocumentCreate,
    DocumentOut,
    GstRegCreate,
    GstRegOut,
    LedgerEntryCreate,
    PartyCreate,
    PartyDetail,
    PartyLedgerOut,
    PartyListItem,
    PartyOut,
    PartyUpdate,
    TagAssignIn,
    TagRef,
)

router = APIRouter()


def _read(perm: str = "party.read"):
    return require_permission(perm)


def _write(perm: str = "party.create"):
    return require_permission(perm)


# ---- party ----
@router.post("", response_model=PartyOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: PartyCreate,
    request: Request,
    principal: Principal = Depends(_write()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_party(session, principal, payload, request.state.idempotency_key)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("", response_model=list[PartyListItem])
async def list_(
    q: str | None = None,
    area: str | None = None,
    is_active: bool | None = None,
    serving_branch_id: int | None = None,
    tag_id: int | None = None,
    sort: str = "created",
    direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(_read()),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_parties(
        session, principal, q,
        area=area, is_active=is_active,
        serving_branch_id=serving_branch_id, tag_id=tag_id,
        sort=sort, direction=direction, limit=limit, offset=offset,
    )


@router.get("/areas", response_model=list[str])
async def areas(
    principal: Principal = Depends(_read()),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_areas(session, principal)


@router.put("/{party_id}", response_model=PartyOut)
async def update(
    party_id: int,
    payload: PartyUpdate,
    principal: Principal = Depends(_write()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.update_party(session, principal, party_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/{party_id}", response_model=PartyDetail)
async def detail(
    party_id: int,
    principal: Principal = Depends(_read()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.get_party_detail(session, party_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


# ---- contacts ----
@router.get("/{party_id}/contacts", response_model=list[ContactOut])
async def contacts_list(party_id: int, principal: Principal = Depends(_read()),
                        session: AsyncSession = Depends(get_scoped_session)):
    return await service.list_contacts(session, party_id)


@router.post("/{party_id}/contacts", response_model=ContactOut, status_code=201)
async def contacts_add(party_id: int, payload: ContactCreate, principal: Principal = Depends(_write()),
                       session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.add_contact(session, principal, party_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


# ---- addresses ----
@router.get("/{party_id}/addresses", response_model=list[AddressOut])
async def addresses_list(party_id: int, principal: Principal = Depends(_read()),
                         session: AsyncSession = Depends(get_scoped_session)):
    return await service.list_addresses(session, party_id)


@router.post("/{party_id}/addresses", response_model=AddressOut, status_code=201)
async def addresses_add(party_id: int, payload: AddressCreate, principal: Principal = Depends(_write()),
                        session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.add_address(session, principal, party_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


# ---- GST registrations ----
@router.get("/{party_id}/gst-registrations", response_model=list[GstRegOut])
async def gst_list(party_id: int, principal: Principal = Depends(_read()),
                   session: AsyncSession = Depends(get_scoped_session)):
    return await service.list_gst(session, party_id)


@router.post("/{party_id}/gst-registrations", response_model=GstRegOut, status_code=201)
async def gst_add(party_id: int, payload: GstRegCreate, principal: Principal = Depends(_write()),
                  session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.add_gst(session, principal, party_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- documents (metadata) ----
@router.get("/{party_id}/documents", response_model=list[DocumentOut])
async def docs_list(party_id: int, principal: Principal = Depends(_read()),
                    session: AsyncSession = Depends(get_scoped_session)):
    return await service.list_documents(session, party_id)


@router.post("/{party_id}/documents", response_model=DocumentOut, status_code=201)
async def docs_add(party_id: int, payload: DocumentCreate, principal: Principal = Depends(_write()),
                   session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.add_document(session, principal, party_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


# ---- tags ----
@router.post("/{party_id}/tags", response_model=list[TagRef])
async def tag_add(party_id: int, payload: TagAssignIn, principal: Principal = Depends(_write()),
                  session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.add_tag(session, principal, party_id, payload.tag_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


@router.delete("/{party_id}/tags/{tag_id}", response_model=list[TagRef])
async def tag_remove(party_id: int, tag_id: int, principal: Principal = Depends(_write()),
                     session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.remove_tag(session, principal, party_id, tag_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


# ---- ledger (receivable / payable) ----
@router.get("/{party_id}/ledger", response_model=PartyLedgerOut)
async def ledger_view(party_id: int, principal: Principal = Depends(_read()),
                      session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.get_ledger(session, principal, party_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")


@router.post("/{party_id}/ledger/entries", response_model=PartyLedgerOut, status_code=201)
async def ledger_add(party_id: int, payload: LedgerEntryCreate, principal: Principal = Depends(_write()),
                     session: AsyncSession = Depends(get_scoped_session)):
    try:
        return await service.post_manual_ledger(session, principal, party_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
