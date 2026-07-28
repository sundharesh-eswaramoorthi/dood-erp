from __future__ import annotations

from pydantic import BaseModel


class UserInfo(BaseModel):
    id: int
    username: str
    full_name: str | None
    org_id: int
    branch_ids: list[int]
    perms: list[str]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str
