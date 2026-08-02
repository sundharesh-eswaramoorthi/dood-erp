from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UnitOfMeasure(Base):
    __tablename__ = "unit_of_measure"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))


class ProductCategory(Base):
    __tablename__ = "product_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("product_category.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("product_category.id"), nullable=True)
    base_unit_id: Mapped[int] = mapped_column(ForeignKey("unit_of_measure.id"))
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    reorder_default: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    hsn_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # v2 §2 pricing master — price_inclusive says whether the two prices above
    # already contain GST, which seeds an invoice's price_mode.
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_inclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    # sub-unit: how many of it make one base unit (1 BAG = 50 KG -> qty 50)
    sub_unit_id: Mapped[int | None] = mapped_column(ForeignKey("unit_of_measure.id"), nullable=True)
    sub_unit_qty: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    opening_qty: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    opening_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    opening_as_of: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    opening_godown_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    opening_branch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnitConversion(Base):
    __tablename__ = "unit_conversion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    from_unit_id: Mapped[int] = mapped_column(ForeignKey("unit_of_measure.id"))
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    effective_from: Mapped[dt.date] = mapped_column(Date, default=dt.date(1, 1, 1))


class ProductPacking(Base):
    __tablename__ = "product_packing"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit_of_measure.id"))
    qty_in_base: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
