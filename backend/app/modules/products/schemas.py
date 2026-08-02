from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    is_active: bool


class ConversionIn(BaseModel):
    from_unit_id: int
    factor_to_base: Decimal = Field(gt=0)


class ProductCreate(BaseModel):
    # v2 §2: optional. Left blank it is allocated from the `product` numbering
    # series, the same gap-free allocator that issues party codes.
    code: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    base_unit_id: int
    category_id: int | None = None
    allow_negative_stock: bool = False
    reorder_default: Decimal | None = None
    hsn_code: str | None = Field(default=None, max_length=20)
    gst_rate: Decimal | None = None
    conversions: list[ConversionIn] = []

    # ---- v2 §2 pricing ----
    sale_price: Decimal | None = Field(default=None, ge=0)
    purchase_price: Decimal | None = Field(default=None, ge=0)
    price_inclusive: bool = False

    # ---- v2 §2 sub-unit (how many sub-units make one base unit) ----
    sub_unit_id: int | None = None
    sub_unit_qty: Decimal | None = Field(default=None, gt=0)

    # ---- v2 §2 stock block ----
    min_stock_qty: Decimal | None = Field(default=None, ge=0)
    opening_qty: Decimal | None = Field(default=None, ge=0)
    opening_rate: Decimal | None = Field(default=None, ge=0)
    opening_as_of: dt.date | None = None
    opening_godown_id: int | None = None
    opening_branch_id: int | None = None   # stock_balance is keyed on both
    is_active: bool = True


class ProductUpdate(BaseModel):
    """v2 §2 "Add / Edit Product" — only the fields sent are changed.

    Opening stock is deliberately absent: it has already moved goods through the
    stock ledger, so it is corrected with a stock adjustment, not by editing the
    product.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = None
    allow_negative_stock: bool | None = None
    hsn_code: str | None = Field(default=None, max_length=20)
    gst_rate: Decimal | None = None
    sale_price: Decimal | None = Field(default=None, ge=0)
    purchase_price: Decimal | None = Field(default=None, ge=0)
    price_inclusive: bool | None = None
    sub_unit_id: int | None = None
    sub_unit_qty: Decimal | None = Field(default=None, gt=0)
    min_stock_qty: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category_id: int | None
    base_unit_id: int
    allow_negative_stock: bool
    reorder_default: Decimal | None
    hsn_code: str | None
    gst_rate: Decimal | None
    is_active: bool
    sale_price: Decimal | None
    purchase_price: Decimal | None
    price_inclusive: bool
    sub_unit_id: int | None
    sub_unit_qty: Decimal | None
    opening_qty: Decimal | None
    opening_rate: Decimal | None
    opening_as_of: dt.date | None
    opening_godown_id: int | None
    opening_branch_id: int | None


class ProductUnitOut(BaseModel):
    """A unit this product may be entered in, and its size in base units."""

    unit_id: int
    code: str
    name: str
    factor_to_base: Decimal
    is_base: bool


class ProductListItem(ProductOut):
    """v2 §2 wants stock quantity and stock value on the product list."""

    stock_qty: Decimal = Decimal(0)
    stock_value: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)
    min_stock_qty: Decimal | None = None
    low_stock: bool = False
    # base unit + every conversion, so an invoice line can offer the sub-unit
    units: list[ProductUnitOut] = []
