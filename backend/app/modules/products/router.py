from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.products.schemas import (
    CategoryCreate,
    CategoryOut,
    ProductCreate,
    ProductListItem,
    ProductOut,
    ProductUpdate,
)
from app.modules.products.service import (
    create_category,
    create_product,
    get_product,
    list_categories,
    list_products,
    update_product,
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
@router.get("", response_model=list[ProductListItem])
async def products_list(
    q: str | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    low_stock: bool | None = None,
    branch_id: int | None = None,
    sort: str = "name",
    direction: str = "asc",
    limit: int = 200,
    offset: int = 0,
    principal: Principal = Depends(require_permission("product.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await list_products(
        session, principal, q,
        category_id=category_id, is_active=is_active, low_stock=low_stock, branch_id=branch_id,
        sort=sort, direction=direction, limit=limit, offset=offset,
    )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def products_create(
    payload: ProductCreate,
    principal: Principal = Depends(require_permission("product.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await create_product(session, principal, payload)
    except PermissionError as e:
        # opening stock posts a real adjustment, which refuses a branch the
        # caller has no access to
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/{product_id}", response_model=ProductOut)
async def products_get(
    product_id: int,
    principal: Principal = Depends(require_permission("product.read")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await get_product(session, product_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")


@router.put("/{product_id}", response_model=ProductOut)
async def products_update(
    product_id: int,
    payload: ProductUpdate,
    principal: Principal = Depends(require_permission("product.create")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await update_product(session, principal, product_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
