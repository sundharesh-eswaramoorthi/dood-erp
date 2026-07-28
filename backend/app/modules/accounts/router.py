from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_principal, get_scoped_session, require_permission
from app.modules.accounts import service
from app.modules.accounts.schemas import AccountCreate, AccountOut, VoucherCreate, VoucherOut

router = APIRouter()


@router.get("/bank-accounts", response_model=list[AccountOut])
async def list_accounts(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_accounts(session, principal)


@router.post("/bank-accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_account(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/payment-vouchers", response_model=VoucherOut, status_code=status.HTTP_201_CREATED)
async def post_voucher(
    payload: VoucherCreate,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_voucher(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/payment-vouchers")
async def list_vouchers(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_vouchers(session, principal)
