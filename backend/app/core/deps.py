from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass
class Principal:
    user_id: int
    org_id: int
    branch_ids: list[int]
    perms: set[str] = field(default_factory=set)
    name: str | None = None

    def has(self, perm: str) -> bool:
        return "*" in self.perms or perm in self.perms


async def get_principal(token: str = Depends(oauth2_scheme)) -> Principal:
    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            raise ValueError("not an access token")
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return Principal(
        user_id=int(payload["sub"]),
        org_id=int(payload["org_id"]),
        branch_ids=[int(b) for b in payload.get("branch_ids", [])],
        perms=set(payload.get("perms", [])),
        name=payload.get("name"),
    )


async def get_scoped_session(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AsyncSession]:
    """Session with Postgres RLS GUCs set for the caller's org + branches.

    set_config(..., is_local => true) scopes the settings to the current
    transaction; the request commits on success, rolls back on error.
    """
    branch_csv = ",".join(str(b) for b in principal.branch_ids) or "-1"
    await session.execute(
        text("SELECT set_config('app.org_id', :o, true), set_config('app.branch_ids', :b, true)"),
        {"o": str(principal.org_id), "b": branch_csv},
    )
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def require_permission(perm: str):
    async def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {perm}")
        return principal

    return _check


def require_any(*perms: str):
    """Any one of these is enough."""

    async def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if not any(principal.has(p) for p in perms):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing permission: one of {', '.join(perms)}"
            )
        return principal

    return _check


def assert_can_edit_dated(principal: Principal, doc_date) -> None:
    """v2 §7: "edit current date invoice" is a different right from "edit
    previous date invoice" — a Sales Executive gets the first and not the
    second, so backdated corrections need a manager.

    Raises 403; call it once the document's own date is known.
    """
    import datetime as _dt

    today = _dt.date.today()
    if doc_date == today:
        needed = "invoice.edit.today"
    else:
        needed = "invoice.edit.backdated"
    if not principal.has(needed):
        when = "today's" if needed.endswith("today") else "a previous date's"
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Missing permission: {needed} (editing {when} document)",
        )


def idempotency_key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")
