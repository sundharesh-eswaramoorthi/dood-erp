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


class BranchOut(BaseModel):
    id: int
    name: str


class GodownOut(BaseModel):
    id: int
    name: str
    branch_id: int


class SettingUpsert(BaseModel):
    value: dict


class SettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: dict
    scope: str
