"""Schema pieces shared by every invoice-shaped document (v2 §3/§4).

Purchase bills, purchase returns, sales bills and sales returns all carry the
same money block, so it is defined once here and mixed in. app.services.money
does the arithmetic these fields feed.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


class MoneyLineIn(BaseModel):
    """Per-line money + placement fields common to all invoice types."""

    godown_id: int | None = None        # v2 "multi godown invoice"; falls back to the header
    discount_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    discount_amount: Decimal | None = None   # explicit wins over pct
    hsn_code: str | None = Field(default=None, max_length=20)
    remarks: str | None = None


class MoneyHeaderIn(BaseModel):
    """Header money block: entry mode, overall discount, charges, settlement."""

    price_mode: str = Field(default="exclusive", pattern="^(exclusive|inclusive)$")
    discount_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    discount_amount: Decimal | None = None
    card_charges: Decimal = Field(default=Decimal(0), ge=0)
    round_off: Decimal | None = None    # None = auto to the nearest rupee
    paid_amount: Decimal = Field(default=Decimal(0), ge=0)
    payment_account_id: int | None = None   # required when paid_amount > 0
    remarks: str | None = None
    doc_datetime: dt.datetime | None = None


class MoneyLineOut(BaseModel):
    line_no: int
    product_id: int
    godown_id: int
    entered_qty: Decimal
    entered_unit_id: int
    base_qty: Decimal
    rate: Decimal
    hsn_code: str | None = None
    remarks: str | None = None
    gross_amount: Decimal
    discount_amount: Decimal
    header_discount_alloc: Decimal
    taxable: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    line_total: Decimal


class MoneyTotalsOut(BaseModel):
    gross_total: Decimal
    line_discount_total: Decimal
    discount_amount: Decimal
    taxable_total: Decimal
    tax_total: Decimal
    card_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    paid_amount: Decimal
    balance_amount: Decimal
