from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.parties.schemas import PartyCreate, PartyOut
from app.modules.parties.service import create_party, list_parties

router = APIRouter()


@router.post("", response_model=PartyOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: PartyCreate,
    request: Request,
    principal: Principal = Depends(require_permission("party.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await create_party(session, principal, payload, request.state.idempotency_key)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("", response_model=list[PartyOut])
async def list_(
    q: str | None = None,
    principal: Principal = Depends(require_permission("party.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await list_parties(session, principal, q)
