from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    party_type: str = Field(default="customer", pattern="^(customer|supplier|both)$")
    gstin: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=20)
    branch_id: int | None = None  # defaults to the caller's first accessible branch


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    party_code: str
    name: str
    party_type: str
    gstin: str | None
    phone: str | None
    branch_id: int
