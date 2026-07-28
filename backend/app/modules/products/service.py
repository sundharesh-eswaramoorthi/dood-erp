from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.product import Product, ProductCategory, UnitConversion, UnitOfMeasure
from app.modules.products.schemas import CategoryCreate, ProductCreate


# ---- categories ----
async def list_categories(session: AsyncSession, principal: Principal) -> list[ProductCategory]:
    stmt = select(ProductCategory).order_by(ProductCategory.name)
    return list((await session.execute(stmt)).scalars().all())


async def create_category(
    session: AsyncSession, principal: Principal, data: CategoryCreate
) -> ProductCategory:
    cat = ProductCategory(org_id=principal.org_id, name=data.name, parent_id=data.parent_id)
    session.add(cat)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError(f"Category '{data.name}' already exists") from e
    return cat


# ---- products ----
async def list_products(session: AsyncSession, principal: Principal, q: str | None = None) -> list[Product]:
    stmt = select(Product).order_by(Product.name).limit(200)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    return list((await session.execute(stmt)).scalars().all())


async def create_product(
    session: AsyncSession, principal: Principal, data: ProductCreate
) -> Product:
    # base unit must exist within the org (RLS-scoped read)
    unit = (
        await session.execute(
            select(UnitOfMeasure).where(UnitOfMeasure.id == data.base_unit_id)
        )
    ).scalar_one_or_none()
    if unit is None:
        raise ValueError("base_unit_id does not exist")

    product = Product(
        org_id=principal.org_id,
        code=data.code,
        name=data.name,
        category_id=data.category_id,
        base_unit_id=data.base_unit_id,
        allow_negative_stock=data.allow_negative_stock,
        reorder_default=data.reorder_default,
        hsn_code=data.hsn_code,
        gst_rate=data.gst_rate,
        created_by=principal.user_id,
    )
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError(f"Product code '{data.code}' already exists") from e

    for conv in data.conversions:
        if conv.from_unit_id == data.base_unit_id:
            continue  # base->base is implicitly 1
        session.add(
            UnitConversion(
                org_id=principal.org_id,
                product_id=product.id,
                from_unit_id=conv.from_unit_id,
                factor_to_base=conv.factor_to_base,
            )
        )
    await session.flush()
    return product
