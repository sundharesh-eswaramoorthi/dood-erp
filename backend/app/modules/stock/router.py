from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.stock import service
from app.modules.stock.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    CurrentStockOut,
    MovementOut,
    TransferCreate,
    TransferOut,
    VerificationCreate,
    VerificationOut,
)
from app.services.stock_engine import OverSell

router = APIRouter()


def _branch(principal: Principal, branch_id: int | None) -> int:
    b = branch_id or (principal.branch_ids[0] if principal.branch_ids else None)
    if b is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no branch")
    return b


@router.post("/adjustments", response_model=AdjustmentOut, status_code=status.HTTP_201_CREATED)
async def post_adjustment(
    payload: AdjustmentCreate,
    principal: Principal = Depends(require_permission("stock.write")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_adjustment(session, principal, payload)
    except OverSell as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/current", response_model=CurrentStockOut)
async def current(
    product_id: int,
    branch_id: int | None = None,
    principal: Principal = Depends(require_permission("stock.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.current_stock(session, principal, product_id, _branch(principal, branch_id))


@router.get("/value")
async def value(
    branch_id: int | None = None,
    principal: Principal = Depends(require_permission("stock.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.stock_value(session, principal, _branch(principal, branch_id))


@router.get("/movements", response_model=list[MovementOut])
async def movements(
    product_id: int,
    branch_id: int | None = None,
    principal: Principal = Depends(require_permission("stock.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_movements(session, principal, product_id, _branch(principal, branch_id))


@router.post("/reconcile")
async def reconcile(
    principal: Principal = Depends(require_permission("stock.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.reconcile(session, principal)


# ---- transfers ----
@router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
async def transfer_create(
    payload: TransferCreate,
    principal: Principal = Depends(require_permission("stock.write")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_transfer(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/transfers/{transfer_id}/dispatch", response_model=TransferOut)
async def transfer_dispatch(
    transfer_id: int,
    principal: Principal = Depends(require_permission("stock.write")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.dispatch_transfer(session, principal, transfer_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    except OverSell as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/transfers/{transfer_id}/receive", response_model=TransferOut)
async def transfer_receive(
    transfer_id: int,
    principal: Principal = Depends(require_permission("stock.write")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.receive_transfer(session, principal, transfer_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- verification (snapshot-delta) ----
@router.post("/verifications", response_model=VerificationOut, status_code=status.HTTP_201_CREATED)
async def verification_create(
    payload: VerificationCreate,
    principal: Principal = Depends(require_permission("stock.write")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_verification(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/verifications/{verification_id}/post", response_model=VerificationOut)
async def verification_post(
    verification_id: int,
    principal: Principal = Depends(require_permission("stock.write")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_verification(session, principal, verification_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
