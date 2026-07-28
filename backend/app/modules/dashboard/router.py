from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_principal, get_scoped_session
from app.modules.dashboard import service

router = APIRouter()


@router.get("")
async def dashboard(
    branch_id: int | None = None,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    b = branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if b is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no branch")
    return await service.get_dashboard(session, principal, b)
