from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.product import Product, ProductCategory, UnitConversion, UnitOfMeasure
from app.modules.products.schemas import CategoryCreate, ProductCreate, ProductUpdate


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
# ORDER BY runs on the OUTER select, so these name the projected columns
# (p.* is unwrapped there) rather than the inner alias.
_SORTS = {
    "name": "lower(name)",
    "code": "code",
    "stock": "stock_qty",
    "value": "stock_value",
}


async def list_products(
    session: AsyncSession,
    principal: Principal,
    q: str | None = None,
    *,
    category_id: int | None = None,
    is_active: bool | None = None,
    low_stock: bool | None = None,
    sort: str = "name",
    direction: str = "asc",
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """v2 §2 product list — with live stock quantity and stock value.

    Stock is summed across every godown the caller can see (stock_balance is
    branch-scoped by RLS); value uses the moving-average cost.
    """
    where = ["TRUE"]
    params: dict = {"limit": min(limit, 500), "offset": max(offset, 0)}
    if q:
        where.append("(p.name ILIKE :q OR p.code ILIKE :q OR p.hsn_code ILIKE :q)")
        params["q"] = f"%{q}%"
    if category_id is not None:
        where.append("p.category_id = :cat")
        params["cat"] = category_id
    if is_active is not None:
        where.append("p.is_active = :active")
        params["active"] = is_active

    order = _SORTS.get(sort, _SORTS["name"])
    order_dir = "ASC" if direction.lower() == "asc" else "DESC"
    having = "WHERE low_stock" if low_stock else ""

    rows = (
        await session.execute(
            text(
                "WITH bal AS ("
                "  SELECT product_id, SUM(on_hand) AS qty FROM stock_balance "
                "  WHERE location_state='on_hand' GROUP BY product_id"
                "), cost AS ("
                "  SELECT product_id, MAX(moving_avg_cost) AS avg_cost FROM product_cost GROUP BY product_id"
                "), thr AS ("
                "  SELECT product_id, MIN(min_qty) AS min_qty FROM reorder_threshold GROUP BY product_id"
                ") "
                "SELECT * FROM ("
                "  SELECT p.*, "
                "         COALESCE(bal.qty, 0)                            AS stock_qty, "
                "         COALESCE(cost.avg_cost, 0)                      AS avg_cost, "
                "         COALESCE(bal.qty, 0) * COALESCE(cost.avg_cost, 0) AS stock_value, "
                "         thr.min_qty                                     AS min_stock_qty, "
                "         (thr.min_qty IS NOT NULL AND COALESCE(bal.qty,0) < thr.min_qty) AS low_stock "
                "  FROM product p "
                "  LEFT JOIN bal  ON bal.product_id  = p.id "
                "  LEFT JOIN cost ON cost.product_id = p.id "
                "  LEFT JOIN thr  ON thr.product_id  = p.id "
                f" WHERE {' AND '.join(where)}"
                ") s "
                f"{having} "
                f"ORDER BY {order} {order_dir} "
                "LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


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
        sale_price=data.sale_price,
        purchase_price=data.purchase_price,
        price_inclusive=data.price_inclusive,
        sub_unit_id=data.sub_unit_id,
        sub_unit_qty=data.sub_unit_qty,
        opening_qty=data.opening_qty,
        opening_rate=data.opening_rate,
        opening_as_of=data.opening_as_of,
        opening_godown_id=data.opening_godown_id,
        is_active=data.is_active,
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

    await _sync_sub_unit(session, principal, product)
    if data.min_stock_qty is not None:
        await _set_min_stock(session, principal, product.id, data.min_stock_qty)
    if data.opening_qty:
        await _post_opening_stock(session, principal, product, data)
    return product


async def _sync_sub_unit(session: AsyncSession, principal: Principal, product: Product) -> None:
    """Mirror the sub-unit into unit_conversion so to_base() handles it.

    sub_unit_qty is sub-units per base unit (1 BAG = 50 KG -> 50); the
    conversion the engine wants is base units per sub-unit, i.e. the reciprocal.
    """
    if not product.sub_unit_id or not product.sub_unit_qty:
        return
    if product.sub_unit_id == product.base_unit_id:
        raise ValueError("sub-unit must differ from the base unit")
    factor = (Decimal(1) / Decimal(product.sub_unit_qty)).quantize(Decimal("0.00000001"))
    await session.execute(
        text(
            "INSERT INTO unit_conversion (org_id, product_id, from_unit_id, factor_to_base) "
            "VALUES (:o,:p,:u,:f) "
            "ON CONFLICT (org_id, product_id, from_unit_id, effective_from) "
            "DO UPDATE SET factor_to_base = EXCLUDED.factor_to_base"
        ),
        {"o": principal.org_id, "p": product.id, "u": product.sub_unit_id, "f": factor},
    )


async def _set_min_stock(
    session: AsyncSession, principal: Principal, product_id: int, min_qty: Decimal
) -> None:
    """v2 §2 "Minimum stock quantity" — the branch-wide reorder threshold
    (godown_id NULL). Delegates to the stock module so there is one writer."""
    from app.modules.stock import service as stock_service
    from app.modules.stock.schemas import ReorderSet

    if not principal.branch_ids:
        return
    await stock_service.set_reorder(
        session, principal, ReorderSet(product_id=product_id, min_qty=min_qty)
    )


async def _post_opening_stock(
    session: AsyncSession, principal: Principal, product: Product, data: ProductCreate
) -> None:
    """Opening stock goes through the real adjustment path, not a direct write —
    so it lands in the stock ledger and the moving average like any other
    movement."""
    from app.modules.stock import service as stock_service
    from app.modules.stock.schemas import AdjustmentCreate, AdjustmentLineIn

    godown_id = data.opening_godown_id
    if godown_id is None:
        godown_id = (
            await session.execute(
                text(
                    "SELECT id FROM godown WHERE org_id=:o AND branch_id = ANY(:b) AND is_active "
                    "ORDER BY id LIMIT 1"
                ),
                {"o": principal.org_id, "b": principal.branch_ids or [-1]},
            )
        ).scalar_one_or_none()
    if godown_id is None:
        raise ValueError("opening stock needs a godown")

    await stock_service.post_adjustment(
        session,
        principal,
        AdjustmentCreate(
            godown_id=godown_id,
            adj_reason="opening",
            effective_date=data.opening_as_of or dt.date.today(),
            note=f"Opening stock for {product.code}",
            lines=[
                AdjustmentLineIn(
                    product_id=product.id,
                    entered_qty=data.opening_qty,
                    entered_unit_id=product.base_unit_id,
                    unit_cost=data.opening_rate or Decimal(0),
                )
            ],
        ),
    )


async def get_product(session: AsyncSession, product_id: int) -> Product:
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        raise LookupError("Product not found")
    return product


async def update_product(
    session: AsyncSession, principal: Principal, product_id: int, data: ProductUpdate
) -> Product:
    product = await get_product(session, product_id)
    fields = data.model_dump(exclude_unset=True)
    min_stock = fields.pop("min_stock_qty", None)

    # these columns are NOT NULL, so an explicit null means "leave alone"
    non_nullable = {"name", "allow_negative_stock", "price_inclusive", "is_active"}
    for key, value in fields.items():
        if value is None and key in non_nullable:
            continue
        setattr(product, key, value)
    await session.flush()

    await _sync_sub_unit(session, principal, product)
    if min_stock is not None:
        await _set_min_stock(session, principal, product.id, min_stock)
    return product
