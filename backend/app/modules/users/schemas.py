from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=4, max_length=200)
    full_name: str | None = Field(default=None, max_length=160)
    is_superuser: bool = False
    role_ids: list[int] = []
    branch_ids: list[int] = []


class UserUpdate(BaseModel):
    """Only the fields sent are changed. role_ids/branch_ids REPLACE the
    existing sets — sending [] clears them, omitting them leaves them alone."""

    full_name: str | None = Field(default=None, max_length=160)
    is_superuser: bool | None = None
    is_active: bool | None = None
    role_ids: list[int] | None = None
    branch_ids: list[int] | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=4, max_length=200)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str | None
    is_superuser: bool
    is_active: bool
    roles: list[str]
    role_ids: list[int]
    branch_ids: list[int]


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    permissions: list[str]


class PermissionOut(BaseModel):
    code: str
    description: str
