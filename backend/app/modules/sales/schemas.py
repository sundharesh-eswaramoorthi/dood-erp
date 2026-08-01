from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.shared import MoneyHeaderIn, MoneyLineIn, MoneyLineOut, MoneyTotalsOut


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
    entered_qty: Decimal
    entered_unit_id: int
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
class BillOrderIn(MoneyHeaderIn):
    """The order supplies the lines; this supplies the v2 §4 money block."""

    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")


class SalesBillLineOut(MoneyLineOut):
    moved_qty: Decimal
    cogs_amount: Decimal


class SalesBillOut(MoneyTotalsOut):
    id: int
    doc_no: str | None
    status: str
    customer_id: int
    supply_type: str
    price_mode: str
    bill_date: dt.date
    doc_datetime: dt.datetime | None = None
    cogs_total: Decimal
    lines: list[SalesBillLineOut]


# ---- sales return ----
class SalesReturnLineIn(MoneyLineIn):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(ge=0)
    gst_rate: Decimal | None = None


class SalesReturnCreate(MoneyHeaderIn):
    customer_id: int
    godown_id: int | None = None
    branch_id: int | None = None
    orig_bill_id: int | None = None
    return_date: dt.date | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    lines: list[SalesReturnLineIn] = Field(min_length=1)


class SalesReturnOut(MoneyTotalsOut):
    id: int
    doc_no: str | None
    status: str
    customer_id: int
    supply_type: str
    price_mode: str
    return_date: dt.date
    doc_datetime: dt.datetime | None = None
    lines: list[MoneyLineOut]
