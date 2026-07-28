from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.units.schemas import UnitCreate, UnitOut
from app.modules.units.service import create_unit, list_units

router = APIRouter()


@router.get("", response_model=list[UnitOut])
async def list_(
    principal: Principal = Depends(require_permission("product.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await list_units(session, principal)


@router.post("", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: UnitCreate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await create_unit(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
