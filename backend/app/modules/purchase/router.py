from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.purchase import service
from app.modules.purchase.schemas import (
    PurchaseBillCreate,
    PurchaseBillOut,
    PurchaseBillWithWarnings,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseReturnCreate,
    PurchaseReturnOut,
    ReceivePOIn,
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


@router.get("/orders/{po_id}", response_model=PurchaseOrderOut)
async def get_order(
    po_id: int,
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.get_po(session, po_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found")


@router.post(
    "/orders/{po_id}/receive",
    response_model=PurchaseBillWithWarnings,
    status_code=status.HTTP_201_CREATED,
)
async def receive_order(
    po_id: int,
    payload: ReceivePOIn | None = None,
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Raise the purchase bill for a PO. Over-receipt warns, it does not block."""
    try:
        return await service.receive_po(session, principal, po_id, payload or ReceivePOIn())
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found")
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/orders/{po_id}/cancel", response_model=PurchaseOrderOut)
async def cancel_order(
    po_id: int,
    principal: Principal = Depends(require_permission("purchase.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.cancel_po(session, principal, po_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
