"""Schema pieces shared by every invoice-shaped document (v2 §3/§4).

Purchase bills, purchase returns, sales bills and sales returns all carry the
same money block, so it is defined once here and mixed in. app.services.money
does the arithmetic these fields feed.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

# The business trades inside one state, so every document is an intra-state
# supply and GST always splits CGST+SGST. Asking the counter to choose between
# "Intra" and "Inter" on every invoice was a question with one answer, so the
# documents no longer accept it and the server decides.
#
# Deliberately a constant and not a deletion: app.services.money still computes
# IGST correctly (see test_money.py) and the igst columns are still written and
# reported. Selling across a state line again means restoring the picker, not
# rebuilding the tax arithmetic.
SUPPLY_TYPE = "intra"


class MoneyLineIn(BaseModel):
    """Per-line money + placement fields common to all invoice types."""

    godown_id: int | None = None        # v2 "multi godown invoice"; falls back to the header
    discount_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    discount_amount: Decimal | None = None   # explicit wins over pct
    hsn_code: str | None = Field(default=None, max_length=20)
    remarks: str | None = None


class PaymentSplitIn(BaseModel):
    """One tender against a document (v2 §3 "split payment").

    account_id says WHERE the money landed, payment_type_id says HOW it was
    taken. They are different questions — two cards and a UPI can all settle
    into the same bank account, and the payment-mode reports need the second.
    """

    account_id: int
    payment_type_id: int | None = None
    amount: Decimal = Field(gt=0)
    reference: str | None = Field(default=None, max_length=120)  # cheque no, UPI ref


class MoneyHeaderIn(BaseModel):
    """Header money block: entry mode, overall discount, charges, settlement."""

    price_mode: str = Field(default="exclusive", pattern="^(exclusive|inclusive)$")
    discount_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    discount_amount: Decimal | None = None
    card_charges: Decimal = Field(default=Decimal(0), ge=0)
    round_off: Decimal | None = None    # None = auto to the nearest rupee
    paid_amount: Decimal = Field(default=Decimal(0), ge=0)
    payment_account_id: int | None = None   # required when paid_amount > 0
    # v2 §3: several tenders on one document. Supplying this replaces the single
    # paid_amount/payment_account_id pair, which stays for the one-tender case.
    payments: list[PaymentSplitIn] = []
    remarks: str | None = None
    doc_datetime: dt.datetime | None = None

    @model_validator(mode="after")
    def _splits_agree_with_paid(self):
        """paid_amount is what the money engine subtracts to get the balance, so
        it has to be exactly what the tenders add up to — otherwise the invoice
        would claim a balance the cash drawer disagrees with."""
        if not self.payments:
            return self
        total = sum((p.amount for p in self.payments), Decimal(0))
        if "paid_amount" in self.model_fields_set and self.paid_amount != total:
            raise ValueError(
                f"the payment split adds up to {total}, but paid_amount says {self.paid_amount}"
            )
        # to the paisa, like the engine downstream — the raw sum of the tenders
        # carries no scale of its own
        from app.services.money import q2

        object.__setattr__(self, "paid_amount", q2(total))
        return self

    def settlement(self) -> list[PaymentSplitIn]:
        """The tenders to post, however the caller expressed them."""
        if self.payments:
            return self.payments
        if self.paid_amount > 0 and self.payment_account_id is not None:
            return [PaymentSplitIn(account_id=self.payment_account_id, amount=self.paid_amount)]
        return []

    def settled_total(self) -> Decimal:
        return sum((p.amount for p in self.settlement()), Decimal(0))


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
