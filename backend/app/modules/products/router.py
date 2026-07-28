from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.products.schemas import (
    CategoryCreate,
    CategoryOut,
    ProductCreate,
    ProductOut,
)
from app.modules.products.service import (
    create_category,
    create_product,
    list_categories,
    list_products,
)

router = APIRouter()


# ---- categories (declared before /{...} product routes) ----
@router.get("/categories", response_model=list[CategoryOut])
async def categories_list(
    principal: Principal = Depends(require_permission("product.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await list_categories(session, principal)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def categories_create(
    payload: CategoryCreate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await create_category(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- products ----
@router.get("", response_model=list[ProductOut])
async def products_list(
    q: str | None = None,
    principal: Principal = Depends(require_permission("product.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await list_products(session, principal, q)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def products_create(
    payload: ProductCreate,
    principal: Principal = Depends(require_permission("product.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await create_product(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
