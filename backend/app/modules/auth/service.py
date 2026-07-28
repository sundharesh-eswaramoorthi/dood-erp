from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.models.user import AppUser
from app.modules.auth.schemas import TokenResponse, UserInfo


async def authenticate(session: AsyncSession, username: str, password: str) -> AppUser | None:
    user = (
        await session.execute(select(AppUser).where(AppUser.username == username))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def _branch_ids(session: AsyncSession, user_id: int) -> list[int]:
    rows = (
        await session.execute(
            text("SELECT branch_id FROM user_branch_access WHERE user_id = :u ORDER BY branch_id"),
            {"u": user_id},
        )
    ).scalars().all()
    return [int(b) for b in rows]


async def _perms(session: AsyncSession, user: AppUser) -> list[str]:
    if user.is_superuser:
        return ["*"]
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT rp.permission_code
                FROM user_role ur
                JOIN role_permission rp ON rp.role_id = ur.role_id
                WHERE ur.user_id = :u
                """
            ),
            {"u": user.id},
        )
    ).scalars().all()
    return [str(p) for p in rows]


async def build_login(session: AsyncSession, user: AppUser) -> TokenResponse:
    branch_ids = await _branch_ids(session, user.id)
    perms = await _perms(session, user)
    claims = {
        "org_id": user.org_id,
        "branch_ids": branch_ids,
        "perms": perms,
        "name": user.full_name,
    }
    return TokenResponse(
        access_token=create_access_token(str(user.id), claims),
        refresh_token=create_refresh_token(str(user.id)),
        user=UserInfo(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            org_id=user.org_id,
            branch_ids=branch_ids,
            perms=perms,
        ),
    )
