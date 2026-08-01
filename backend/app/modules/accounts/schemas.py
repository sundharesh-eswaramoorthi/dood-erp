from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account_type: str = Field(pattern="^(bank|cash|petty_cash)$")
    opening_balance: Decimal = Field(default=Decimal(0))


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    account_type: str
    current_balance: Decimal


class AllocationIn(BaseModel):
    """Settle a specific outstanding ledger entry (i.e. a specific bill)."""

    against_entry_id: int
    amount: Decimal = Field(gt=0)


class VoucherCreate(BaseModel):
    party_id: int
    account_id: int
    voucher_type: str = Field(pattern="^(receipt|payment)$")
    amount: Decimal = Field(gt=0)
    branch_id: int | None = None
    voucher_date: dt.date | None = None
    note: str | None = None
    payment_type_id: int | None = None          # v2 §3 "Payment type"
    # v2 §3 payment history: which bills this settles. Omit to let it run down
    # the oldest open items first; send [] to leave it on account.
    allocations: list[AllocationIn] | None = None


class AllocationOut(BaseModel):
    against_entry_id: int
    amount: Decimal
    doc_type: str
    doc_id: int


class VoucherOut(BaseModel):
    id: int
    doc_no: str | None
    voucher_type: str
    party_id: int
    account_id: int
    amount: Decimal
    account_balance: Decimal
    party_net: Decimal
    payment_type_id: int | None = None
    allocations: list[AllocationOut] = []
    unallocated: Decimal = Decimal(0)


# ---- payment types (v2 §3 "add payment type") ----
class PaymentTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="other", pattern="^(cash|bank|card|upi|cheque|credit|other)$")
    default_account_id: int | None = None
    sort_order: int = 0


class PaymentTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: str | None = Field(default=None, pattern="^(cash|bank|card|upi|cheque|credit|other)$")
    default_account_id: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class PaymentTypeOut(BaseModel):
    id: int
    name: str
    kind: str
    default_account_id: int | None
    is_active: bool
    sort_order: int


class OpenItemOut(BaseModel):
    entry_id: int
    source_doc_type: str
    source_doc_id: int
    effective_date: dt.date
    amount: Decimal
    settled: Decimal
    outstanding: Decimal


class ExpenseCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ExpenseCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ExpenseCreate(BaseModel):
    account_id: int
    amount: Decimal = Field(gt=0)
    category_id: int | None = None
    branch_id: int | None = None
    expense_date: dt.date | None = None
    note: str | None = None


class ExpenseOut(BaseModel):
    id: int
    doc_no: str | None
    amount: Decimal
    account_id: int
    category_id: int | None
    account_balance: Decimal
