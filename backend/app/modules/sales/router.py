from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.sales import service
from app.modules.sales.schemas import (
    BillOrderIn,
    DeliveryCreate,
    DirectBillCreate,
    DeliveryOut,
    SaleOrderCreate,
    SaleOrderOut,
    SalesBillOut,
    SalesReturnCreate,
    SalesReturnOut,
)
from app.services.credit import CreditLimitExceeded
from app.services.stock_engine import OverSell

router = APIRouter()


@router.post("/orders", response_model=SaleOrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: SaleOrderCreate,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_order(session, principal, payload)
    except (OverSell, CreditLimitExceeded) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/orders")
async def list_orders(
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_orders(session, principal)


@router.get("/orders/{order_id}", response_model=SaleOrderOut)
async def get_order(
    order_id: int,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.get_order(session, order_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")


@router.post("/orders/{order_id}/cancel", response_model=SaleOrderOut)
async def cancel_order(
    order_id: int,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.cancel_order(session, principal, order_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/orders/{order_id}/deliver", response_model=DeliveryOut, status_code=201)
async def deliver_full(
    order_id: int,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.deliver_full(session, principal, order_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    except service.OverFulfil as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except OverSell as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- deliveries (explicit / partial) ----
@router.post("/deliveries", response_model=DeliveryOut, status_code=201)
async def create_delivery(
    payload: DeliveryCreate,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_delivery(session, principal, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/deliveries/{delivery_id}/dispatch", response_model=DeliveryOut)
async def dispatch_delivery(
    delivery_id: int,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.dispatch_delivery(session, principal, delivery_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    except service.OverFulfil as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except OverSell as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/deliveries/{delivery_id}/complete", response_model=DeliveryOut)
async def complete_delivery(
    delivery_id: int,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.complete_delivery(session, principal, delivery_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/deliveries")
async def list_deliveries(
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_deliveries(session, principal)


# ---- sales bills & returns ----
@router.post("/orders/{order_id}/bill", response_model=SalesBillOut, status_code=201)
async def bill_order(
    order_id: int,
    payload: BillOrderIn | None = None,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.bill_order(session, principal, order_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    except (OverSell, CreditLimitExceeded) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/bills", response_model=SalesBillOut, status_code=status.HTTP_201_CREATED)
async def create_direct_bill(
    payload: DirectBillCreate,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    """v2 §4 counter sale — an invoice with no order behind it. The bill moves
    the stock itself, since nothing reserved or delivered it."""
    try:
        return await service.post_direct_bill(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except (OverSell, CreditLimitExceeded) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/bills")
async def list_bills(
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_bills(session, principal)


@router.post("/returns", response_model=SalesReturnOut, status_code=201)
async def create_return(
    payload: SalesReturnCreate,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.post_sales_return(session, principal, payload)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except OverSell as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/bills/{bill_id}/payments")
async def bill_payments(
    bill_id: int,
    principal: Principal = Depends(require_permission("sales.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    """v2 §3 "Payment history" — what has settled this invoice, and what is left."""
    from app.services import allocation as alloc

    return await alloc.document_payments(session, principal.org_id, "sales_bill", bill_id)
