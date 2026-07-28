from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


class BillLineIn(BaseModel):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(ge=0)              # ex-tax price per entered unit
    gst_rate: Decimal | None = None          # falls back to product.gst_rate


class PurchaseBillCreate(BaseModel):
    supplier_id: int
    godown_id: int
    branch_id: int | None = None
    supplier_invoice_no: str | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    bill_date: dt.date | None = None
    lines: list[BillLineIn] = Field(min_length=1)


class BillLineOut(BaseModel):
    line_no: int
    product_id: int
    base_qty: Decimal
    rate: Decimal
    taxable: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    line_total: Decimal


class PurchaseBillOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    supplier_id: int
    taxable_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
    lines: list[BillLineOut]
