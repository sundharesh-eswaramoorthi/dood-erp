from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.shared import MoneyHeaderIn, MoneyLineIn, MoneyLineOut, MoneyTotalsOut


class OrderLineIn(MoneyLineIn):
    product_id: int
    godown_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(default=Decimal(0), ge=0)
    gst_rate: Decimal | None = None


class SaleOrderCreate(MoneyHeaderIn):
    customer_id: int
    branch_id: int | None = None
    order_date: dt.date | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    note: str | None = None
    lines: list[OrderLineIn] = Field(min_length=1)

    # an order takes no money; the bill does
    paid_amount: Decimal = Field(default=Decimal(0), ge=0, exclude=True)


class OrderLineOut(BaseModel):
    line_no: int
    product_id: int
    godown_id: int
    entered_qty: Decimal
    entered_unit_id: int
    base_qty: Decimal
    rate: Decimal
    hsn_code: str | None = None
    remarks: str | None = None
    gross_amount: Decimal = Decimal(0)
    discount_amount: Decimal = Decimal(0)
    header_discount_alloc: Decimal = Decimal(0)
    taxable: Decimal = Decimal(0)
    gst_rate: Decimal = Decimal(0)
    cgst: Decimal = Decimal(0)
    sgst: Decimal = Decimal(0)
    igst: Decimal = Decimal(0)
    line_total: Decimal = Decimal(0)


class SaleOrderOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    customer_id: int
    supply_type: str = "intra"
    price_mode: str = "exclusive"
    order_date: dt.date | None = None
    gross_total: Decimal = Decimal(0)
    line_discount_total: Decimal = Decimal(0)
    discount_amount: Decimal = Decimal(0)
    taxable_total: Decimal = Decimal(0)
    tax_total: Decimal = Decimal(0)
    card_charges: Decimal = Decimal(0)
    round_off: Decimal = Decimal(0)
    grand_total: Decimal = Decimal(0)
    note: str | None = None
    lines: list[OrderLineOut]


# ---- counter / direct sale: a bill with no order behind it ----
class DirectBillLineIn(MoneyLineIn):
    product_id: int
    godown_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(ge=0)
    gst_rate: Decimal | None = None


class DirectBillCreate(MoneyHeaderIn):
    """v2 §4 sale invoice raised without an order (walk-in / counter sale).

    With no order there is no reservation and no delivery, so the bill is the
    sole mover of the goods — the same rule decision #5 already applies when a
    bill runs ahead of its delivery.
    """

    customer_id: int
    branch_id: int | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    bill_date: dt.date | None = None
    lines: list[DirectBillLineIn] = Field(min_length=1)


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
