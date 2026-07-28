from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.purchase import service
from app.modules.purchase.schemas import PurchaseBillCreate, PurchaseBillOut

router = APIRouter()


@router.post("/bills", response_model=PurchaseBillOut, status_code=status.HTTP_201_CREATED)
async def create_bill(
    payload: PurchaseBillCreate,
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_bill(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/bills")
async def list_bills(
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_bills(session, principal)
