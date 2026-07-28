from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


class OrderLineIn(BaseModel):
    product_id: int
    godown_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(default=Decimal(0), ge=0)


class SaleOrderCreate(BaseModel):
    customer_id: int
    branch_id: int | None = None
    order_date: dt.date | None = None
    note: str | None = None
    lines: list[OrderLineIn] = Field(min_length=1)


class OrderLineOut(BaseModel):
    line_no: int
    product_id: int
    godown_id: int
    base_qty: Decimal
    rate: Decimal


class SaleOrderOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    customer_id: int
    lines: list[OrderLineOut]


# ---- delivery ----
class DeliveryLineIn(BaseModel):
    sale_order_line_no: int
    qty: Decimal = Field(gt=0)  # base units


class DeliveryCreate(BaseModel):
    sale_order_id: int
    delivery_boy_id: int | None = None
    lines: list[DeliveryLineIn] = Field(min_length=1)


class DeliveryLineOut(BaseModel):
    line_no: int
    sale_order_line_no: int
    product_id: int
    godown_id: int
    base_qty: Decimal


class DeliveryOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    sale_order_id: int
    lines: list[DeliveryLineOut]


# ---- sales bill (from an order) ----
class BillOrderIn(BaseModel):
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")


class SalesBillLineOut(BaseModel):
    line_no: int
    product_id: int
    base_qty: Decimal
    moved_qty: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    cogs_amount: Decimal
    line_total: Decimal


class SalesBillOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    customer_id: int
    taxable_total: Decimal
    tax_total: Decimal
    cogs_total: Decimal
    grand_total: Decimal
    lines: list[SalesBillLineOut]


# ---- sales return ----
class SalesReturnLineIn(BaseModel):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(ge=0)
    gst_rate: Decimal | None = None


class SalesReturnCreate(BaseModel):
    customer_id: int
    godown_id: int
    branch_id: int | None = None
    orig_bill_id: int | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    lines: list[SalesReturnLineIn] = Field(min_length=1)


class SalesReturnOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    customer_id: int
    taxable_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
