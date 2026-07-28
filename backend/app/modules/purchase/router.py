from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.purchase import service
from app.modules.purchase.schemas import (
    PurchaseBillCreate,
    PurchaseBillOut,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseReturnCreate,
    PurchaseReturnOut,
)

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


# ---- returns ----
@router.post("/returns", response_model=PurchaseReturnOut, status_code=status.HTTP_201_CREATED)
async def create_return(
    payload: PurchaseReturnCreate,
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_return(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except service.eng.OverSell as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- purchase orders (optional / feature-flagged) ----
@router.post("/orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: PurchaseOrderCreate,
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_po(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/orders")
async def list_orders(
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_po(session, principal)
