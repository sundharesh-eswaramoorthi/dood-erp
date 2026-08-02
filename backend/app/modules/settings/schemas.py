from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TaxRateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rate: Decimal = Field(ge=0)


class TaxRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rate: Decimal
    is_active: bool


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#B96D28", max_length=20)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    is_active: bool


# ---- branches (v2 §9 "Add branch") ----
class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=20)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=20)
    gstin: str | None = Field(default=None, max_length=15)
    state_code: str | None = Field(default=None, max_length=2)
    is_active: bool = True


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=20)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=20)
    gstin: str | None = Field(default=None, max_length=15)
    state_code: str | None = Field(default=None, max_length=2)
    is_active: bool | None = None


class BranchOut(BaseModel):
    id: int
    name: str
    code: str | None = None
    address: str | None = None
    phone: str | None = None
    gstin: str | None = None
    state_code: str | None = None
    is_active: bool = True


# ---- godowns (v2 §2 "Godown management") ----
class GodownCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    branch_id: int
    code: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class GodownUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    branch_id: int | None = None
    code: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class GodownOut(BaseModel):
    id: int
    name: str
    branch_id: int
    code: str | None = None
    is_active: bool = True


# ---- document types (v2 §9 "Add documents (customisable)") ----
class DocumentTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    applies_to: str = Field(default="party", pattern="^(party|product|branch)$")
    is_required: bool = False
    sort_order: int = 0


class DocumentTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_required: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class DocumentTypeOut(BaseModel):
    id: int
    name: str
    applies_to: str
    is_required: bool
    is_active: bool
    sort_order: int


class SettingUpsert(BaseModel):
    value: dict


class SettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: dict
    scope: str


# ---- document numbering (v2 §9 "customisable document numbers") ----
class NumberingSeriesOut(BaseModel):
    id: int
    doc_type: str
    label: str           # human name for doc_type, e.g. "Sales invoice"
    fin_year: str
    prefix: str
    pad_width: int
    next_value: int
    branch_id: int | None
    sample: str          # what the next allocated number will look like


class NumberingSeriesUpdate(BaseModel):
    """next_value moves forward only — see the service for why."""

    prefix: str | None = Field(default=None, max_length=20)
    pad_width: int | None = Field(default=None, ge=1, le=12)
    next_value: int | None = Field(default=None, ge=1)
