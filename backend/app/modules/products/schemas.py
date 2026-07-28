from __future__ import annotations

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
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    base_unit_id: int
    category_id: int | None = None
    allow_negative_stock: bool = False
    reorder_default: Decimal | None = None
    hsn_code: str | None = Field(default=None, max_length=20)
    gst_rate: Decimal | None = None
    conversions: list[ConversionIn] = []


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
