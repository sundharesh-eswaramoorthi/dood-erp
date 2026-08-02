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
    # which PO line this receipt satisfies; only meaningful when billing a PO
    po_line_no: int | None = None


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
class POLineIn(MoneyLineIn):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    rate: Decimal = Field(default=Decimal(0), ge=0)
    gst_rate: Decimal | None = None


class PurchaseOrderCreate(MoneyHeaderIn):
    """v2 §3: same shape as a bill, except the money up front is an ADVANCE."""

    supplier_id: int
    godown_id: int | None = None
    branch_id: int | None = None
    supply_type: str = Field(default="intra", pattern="^(intra|inter)$")
    order_date: dt.date | None = None
    expected_date: dt.date | None = None
    note: str | None = None
    advance_amount: Decimal = Field(default=Decimal(0), ge=0)
    lines: list[POLineIn] = Field(min_length=1)

    # a PO is not paid, it is advanced against
    paid_amount: Decimal = Field(default=Decimal(0), ge=0, exclude=True)

    def settlement(self):
        """The advance is this document's tender, so a split advance splits the
        same way a split payment does."""
        from app.modules.shared import PaymentSplitIn

        if self.payments:
            return self.payments
        if self.advance_amount > 0 and self.payment_account_id is not None:
            return [PaymentSplitIn(account_id=self.payment_account_id,
                                   amount=self.advance_amount)]
        return []


class POLineOut(MoneyLineOut):
    received_qty: Decimal = Decimal(0)
    pending_qty: Decimal = Decimal(0)


class PurchaseOrderOut(BaseModel):
    id: int
    doc_no: str | None
    status: str
    supplier_id: int
    supply_type: str = "intra"
    price_mode: str = "exclusive"
    order_date: dt.date | None = None
    expected_date: dt.date | None = None
    gross_total: Decimal = Decimal(0)
    line_discount_total: Decimal = Decimal(0)
    discount_amount: Decimal = Decimal(0)
    taxable_total: Decimal = Decimal(0)
    tax_total: Decimal = Decimal(0)
    card_charges: Decimal = Decimal(0)
    round_off: Decimal = Decimal(0)
    grand_total: Decimal = Decimal(0)
    advance_amount: Decimal = Decimal(0)
    balance_amount: Decimal = Decimal(0)
    note: str | None = None
    lines: list[POLineOut] = []


class ReceivePOIn(MoneyHeaderIn):
    """Turn a PO into a purchase bill. Lines default to everything still
    pending; send `lines` to receive a partial delivery."""

    supplier_invoice_no: str | None = None
    bill_date: dt.date | None = None
    supply_type: str | None = None          # defaults to the PO's
    lines: list[BillLineIn] | None = None   # None = receive the whole balance


class PurchaseBillWithWarnings(PurchaseBillOut):
    """Decision #10: over-receipt warns, it does not block."""

    warnings: list[str] = []
