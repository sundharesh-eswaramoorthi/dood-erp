from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.shared import MoneyHeaderIn, MoneyLineIn, MoneyLineOut, MoneyTotalsOut


class BillLineIn(MoneyLineIn):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(ge=0)              # price per ENTERED unit
    gst_rate: Decimal | None = None          # falls back to product.gst_rate


class PurchaseBillCreate(MoneyHeaderIn):
    supplier_id: int
    godown_id: int | None = None             # default godown for lines that omit one
    branch_id: int | None = None
    supplier_invoice_no: str | None = None
    po_id: int | None = None                 # v2 §3 "PO number"
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    bill_date: dt.date | None = None
    lines: list[BillLineIn] = Field(min_length=1)


class BillLineOut(MoneyLineOut):
    pass


class PurchaseBillOut(MoneyTotalsOut):
    id: int
    doc_no: str | None
    status: str
    supplier_id: int
    supply_type: str
    price_mode: str
    bill_date: dt.date
    doc_datetime: dt.datetime | None = None
    po_id: int | None = None
    lines: list[BillLineOut]


# ---- returns ----
class PurchaseReturnCreate(MoneyHeaderIn):
    supplier_id: int
    godown_id: int | None = None
    branch_id: int | None = None
    orig_bill_id: int | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    return_date: dt.date | None = None
    lines: list[BillLineIn] = Field(min_length=1)


class PurchaseReturnOut(MoneyTotalsOut):
    id: int
    doc_no: str | None
    status: str
    supplier_id: int
    supply_type: str
    price_mode: str
    return_date: dt.date
    doc_datetime: dt.datetime | None = None
    lines: list[BillLineOut]


# ---- purchase order (optional / feature-flagged) ----
class POLineIn(BaseModel):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(default=Decimal(0), ge=0)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    branch_id: int | None = None
    order_date: dt.date | None = None
    expected_date: dt.date | None = None
    note: str | None = None
    lines: list[POLineIn] = Field(min_length=1)


class PurchaseOrderOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    supplier_id: int
