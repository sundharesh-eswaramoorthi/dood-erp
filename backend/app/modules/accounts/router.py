from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_principal, get_scoped_session, require_permission
from app.modules.accounts import service
from app.modules.accounts.schemas import (
    AccountCreate,
    AccountOut,
    AllocationIn,
    ExpenseCategoryCreate,
    ExpenseCategoryOut,
    ExpenseCreate,
    ExpenseOut,
    OpenItemOut,
    PaymentTypeCreate,
    PaymentTypeOut,
    PaymentTypeUpdate,
    VoucherCreate,
    VoucherOut,
)
from app.services.allocation import AllocationError

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


# ---- expenses ----
@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
async def list_expense_categories(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_expense_categories(session, principal)


@router.post("/expense-categories", response_model=ExpenseCategoryOut, status_code=201)
async def create_expense_category(
    payload: ExpenseCategoryCreate,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_expense_category(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
async def post_expense(
    payload: ExpenseCreate,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_expense(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/expenses")
async def list_expenses(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_expenses(session, principal)


# ---- payment types (v2 §3 "add payment type") ----
@router.get("/payment-types", response_model=list[PaymentTypeOut])
async def payment_types_list(
    include_inactive: bool = False,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_payment_types(session, principal, include_inactive)


@router.post("/payment-types", response_model=PaymentTypeOut, status_code=status.HTTP_201_CREATED)
async def payment_types_create(
    payload: PaymentTypeCreate,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_payment_type(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.put("/payment-types/{pt_id}", response_model=PaymentTypeOut)
async def payment_types_update(
    pt_id: int,
    payload: PaymentTypeUpdate,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.update_payment_type(session, principal, pt_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- bill-wise settlement (v2 §3 payment history) ----
@router.get("/parties/{party_id}/open-items", response_model=list[OpenItemOut])
async def open_items(
    party_id: int,
    side: str = "debit",
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Bills this party still owes on ('debit'), or that we owe them ('credit')."""
    return await service.party_open_items(session, principal, party_id, side)


@router.post("/vouchers/{voucher_id}/allocate")
async def allocate_voucher(
    voucher_id: int,
    allocations: list[AllocationIn] | None = None,
    principal: Principal = Depends(require_permission("accounts.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Apply an already-posted receipt/payment to specific bills. Send nothing
    to run it down the oldest open items."""
    try:
        return await service.allocate_voucher(session, principal, voucher_id, allocations)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment voucher not found")
    except AllocationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
