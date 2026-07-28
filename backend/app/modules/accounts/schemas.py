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


class VoucherCreate(BaseModel):
    party_id: int
    account_id: int
    voucher_type: str = Field(pattern="^(receipt|payment)$")
    amount: Decimal = Field(gt=0)
    branch_id: int | None = None
    voucher_date: dt.date | None = None
    note: str | None = None


class VoucherOut(BaseModel):
    id: int
    doc_no: str | None
    voucher_type: str
    party_id: int
    account_id: int
    amount: Decimal
    account_balance: Decimal
    party_net: Decimal


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
