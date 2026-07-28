from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


class AdjustmentLineIn(BaseModel):
    product_id: int
    entered_qty: Decimal = Field(gt=0)
    entered_unit_id: int
    unit_cost: Decimal | None = None  # required for increase/opening


class AdjustmentCreate(BaseModel):
    godown_id: int
    adj_reason: str = Field(pattern="^(increase|decrease|damage|shortage|opening)$")
    branch_id: int | None = None
    effective_date: dt.date | None = None
    note: str | None = None
    lines: list[AdjustmentLineIn] = Field(min_length=1)


class AdjustmentLineOut(BaseModel):
    line_no: int
    product_id: int
    base_qty: Decimal
    unit_cost: Decimal | None


class AdjustmentOut(BaseModel):
    id: int
    doc_no: str | None
    adj_reason: str
    status: str
    lines: list[AdjustmentLineOut]


class GodownStock(BaseModel):
    godown_id: int
    on_hand: Decimal
    reserved: Decimal
    available: Decimal


class CurrentStockOut(BaseModel):
    product_id: int
    branch_id: int
    total_on_hand: Decimal
    total_reserved: Decimal
    total_available: Decimal
    by_godown: list[GodownStock]


class MovementOut(BaseModel):
    id: int
    godown_id: int
    signed_qty: Decimal
    unit_cost: Decimal | None
    movement_type: str
    source_doc_type: str
    source_doc_id: int
    effective_date: dt.date
