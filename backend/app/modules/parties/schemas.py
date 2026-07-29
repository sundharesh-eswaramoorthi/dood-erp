from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    party_type: str = Field(default="customer", pattern="^(customer|supplier|both)$")
    gstin: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=20)
    pan: str | None = Field(default=None, max_length=20)
    credit_limit: Decimal | None = None
    branch_id: int | None = None


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    party_code: str
    name: str
    party_type: str
    gstin: str | None
    phone: str | None
    pan: str | None
    credit_limit: Decimal | None
    branch_id: int


# ---- contacts ----
class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=160)
    designation: str | None = Field(default=None, max_length=80)
    is_primary: bool = False


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    email: str | None
    designation: str | None
    is_primary: bool


# ---- addresses (with geo) ----
class AddressCreate(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, max_length=12)
    lat: Decimal | None = None
    lng: Decimal | None = None
    place_id: str | None = Field(default=None, max_length=200)
    is_default: bool = False


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str | None
    line1: str
    line2: str | None
    city: str | None
    state: str | None
    pincode: str | None
    lat: Decimal | None
    lng: Decimal | None
    place_id: str | None
    is_default: bool


# ---- GST registrations ----
class GstRegCreate(BaseModel):
    gstin: str = Field(min_length=15, max_length=15)
    state_code: str | None = Field(default=None, max_length=2)
    legal_name: str | None = Field(default=None, max_length=200)
    is_default: bool = False


class GstRegOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gstin: str
    state_code: str | None
    legal_name: str | None
    is_default: bool


# ---- documents (metadata) ----
class DocumentCreate(BaseModel):
    doc_type: str = Field(min_length=1, max_length=40)
    file_name: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=400)
    content_type: str | None = Field(default=None, max_length=120)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: str
    file_name: str
    storage_key: str
    content_type: str | None


class TagRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str


class TagAssignIn(BaseModel):
    tag_id: int


class PartyDetail(PartyOut):
    contacts: list[ContactOut] = []
    addresses: list[AddressOut] = []
    gst_registrations: list[GstRegOut] = []
    documents: list[DocumentOut] = []
    tags: list[TagRef] = []


# ---- party ledger ----
class LedgerEntryCreate(BaseModel):
    entry_side: str = Field(pattern="^(debit|credit)$")
    amount: Decimal = Field(gt=0)
    note: str | None = None
    effective_date: dt.date | None = None
    gst_registration_id: int | None = None


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_side: str
    amount: Decimal
    source_doc_type: str
    source_doc_id: int
    effective_date: dt.date


class PartyLedgerOut(BaseModel):
    party_id: int
    net_balance: Decimal
    receivable: Decimal
    payable: Decimal
    entries: list[LedgerEntryOut]
