"""User & role administration (§7). The RBAC enforcement already lives in
app.core.deps; this exposes managing users, their roles, and branch access.
Identity tables aren't RLS-scoped, so queries filter org_id explicitly.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.core.security import hash_password
from app.modules.users.schemas import UserCreate


async def get_user(session: AsyncSession, org_id: int, user_id: int) -> dict:
    return dict(
        (
            await session.execute(
                text(
                    "SELECT u.id, u.username, u.full_name, u.is_superuser, u.is_active, "
                    "ARRAY(SELECT r.code FROM user_role ur JOIN role r ON r.id=ur.role_id WHERE ur.user_id=u.id) AS roles, "
                    "ARRAY(SELECT branch_id FROM user_branch_access WHERE user_id=u.id) AS branch_ids "
                    "FROM app_user u WHERE u.org_id=:o AND u.id=:i"
                ),
                {"o": org_id, "i": user_id},
            )
        ).mappings().one()
    )


async def list_users(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT u.id, u.username, u.full_name, u.is_superuser, u.is_active, "
                "ARRAY(SELECT r.code FROM user_role ur JOIN role r ON r.id=ur.role_id WHERE ur.user_id=u.id) AS roles, "
                "ARRAY(SELECT branch_id FROM user_branch_access WHERE user_id=u.id) AS branch_ids "
                "FROM app_user u WHERE u.org_id=:o ORDER BY u.id"
            ),
            {"o": principal.org_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_user(session: AsyncSession, principal: Principal, data: UserCreate) -> dict:
    exists = (
        await session.execute(text("SELECT 1 FROM app_user WHERE username=:u"), {"u": data.username})
    ).scalar_one_or_none()
    if exists:
        raise ValueError(f"Username '{data.username}' is taken")
    uid = (
        await session.execute(
            text(
                "INSERT INTO app_user (org_id, username, password_hash, full_name, is_superuser) "
                "VALUES (:o,:u,:p,:n,:su) RETURNING id"
            ),
            {"o": principal.org_id, "u": data.username, "p": hash_password(data.password),
             "n": data.full_name, "su": data.is_superuser},
        )
    ).scalar_one()
    for rid in data.role_ids:
        await session.execute(
            text("INSERT INTO user_role (user_id, role_id) VALUES (:u,:r) ON CONFLICT DO NOTHING"),
            {"u": uid, "r": rid},
        )
    for bid in data.branch_ids:
        await session.execute(
            text("INSERT INTO user_branch_access (user_id, branch_id) VALUES (:u,:b) ON CONFLICT DO NOTHING"),
            {"u": uid, "b": bid},
        )
    return await get_user(session, principal.org_id, uid)


async def list_roles(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT r.id, r.code, r.name, "
                "ARRAY(SELECT permission_code FROM role_permission WHERE role_id=r.id ORDER BY permission_code) AS permissions "
                "FROM role r WHERE r.org_id=:o ORDER BY r.id"
            ),
            {"o": principal.org_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_permissions(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (await session.execute(text("SELECT code, description FROM permission ORDER BY code"))).mappings().all()
    return [dict(r) for r in rows]
