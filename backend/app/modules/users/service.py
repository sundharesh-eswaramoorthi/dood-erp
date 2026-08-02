"""User & role administration (§7). The RBAC enforcement already lives in
app.core.deps; this exposes managing users, their roles, and branch access.
Identity tables aren't RLS-scoped, so queries filter org_id explicitly.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.core.security import hash_password
from app.modules.users.schemas import UserCreate, UserUpdate

USER_COLS = (
    "u.id, u.username, u.full_name, u.is_superuser, u.is_active, "
    "ARRAY(SELECT r.code FROM user_role ur JOIN role r ON r.id=ur.role_id WHERE ur.user_id=u.id) AS roles, "
    "ARRAY(SELECT ur.role_id FROM user_role ur WHERE ur.user_id=u.id) AS role_ids, "
    "ARRAY(SELECT branch_id FROM user_branch_access WHERE user_id=u.id) AS branch_ids"
)


async def get_user(session: AsyncSession, org_id: int, user_id: int) -> dict:
    row = (
        await session.execute(
            text(f"SELECT {USER_COLS} FROM app_user u WHERE u.org_id=:o AND u.id=:i"),
            {"o": org_id, "i": user_id},
        )
    ).mappings().first()
    if row is None:
        raise LookupError("User not found")
    return dict(row)


async def list_users(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text(f"SELECT {USER_COLS} FROM app_user u WHERE u.org_id=:o ORDER BY u.id"),
            {"o": principal.org_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _validate_access(
    session: AsyncSession, org_id: int, role_ids: list[int], branch_ids: list[int], is_superuser: bool
) -> None:
    """Reject unknown or out-of-org ids up front.

    Letting them through hits the foreign keys and surfaces as a 500 with no
    hint of which id was wrong.
    """
    if role_ids:
        found = set(
            (
                await session.execute(
                    text("SELECT id FROM role WHERE org_id=:o AND id = ANY(:r)"),
                    {"o": org_id, "r": role_ids},
                )
            ).scalars().all()
        )
        missing = sorted(set(role_ids) - found)
        if missing:
            raise ValueError(f"Unknown role id(s): {', '.join(map(str, missing))}")
    if branch_ids:
        found = set(
            (
                await session.execute(
                    text("SELECT id FROM branch WHERE org_id=:o AND id = ANY(:b)"),
                    {"o": org_id, "b": branch_ids},
                )
            ).scalars().all()
        )
        missing = sorted(set(branch_ids) - found)
        if missing:
            raise ValueError(f"Unknown branch id(s): {', '.join(map(str, missing))}")

    # A user with no branch sees an empty app and the dashboard refuses to load,
    # and one with no role is refused by every endpoint. Both look like a broken
    # login rather than a misconfigured account, so they are rejected at source.
    if not branch_ids:
        raise ValueError("Give the user access to at least one branch")
    if not role_ids and not is_superuser:
        raise ValueError("Give the user at least one role (or make them a super user)")


async def _set_roles(session: AsyncSession, user_id: int, role_ids: list[int]) -> None:
    await session.execute(text("DELETE FROM user_role WHERE user_id=:u"), {"u": user_id})
    for rid in role_ids:
        await session.execute(
            text("INSERT INTO user_role (user_id, role_id) VALUES (:u,:r) ON CONFLICT DO NOTHING"),
            {"u": user_id, "r": rid},
        )


async def _set_branches(session: AsyncSession, user_id: int, branch_ids: list[int]) -> None:
    await session.execute(text("DELETE FROM user_branch_access WHERE user_id=:u"), {"u": user_id})
    for bid in branch_ids:
        await session.execute(
            text("INSERT INTO user_branch_access (user_id, branch_id) VALUES (:u,:b) ON CONFLICT DO NOTHING"),
            {"u": user_id, "b": bid},
        )


async def create_user(session: AsyncSession, principal: Principal, data: UserCreate) -> dict:
    username = data.username.strip()
    if not username:
        raise ValueError("Username is required")
    exists = (
        await session.execute(text("SELECT 1 FROM app_user WHERE lower(username)=lower(:u)"), {"u": username})
    ).scalar_one_or_none()
    if exists:
        raise ValueError(f"Username '{username}' is taken")
    await _validate_access(session, principal.org_id, data.role_ids, data.branch_ids, data.is_superuser)

    uid = (
        await session.execute(
            text(
                "INSERT INTO app_user (org_id, username, password_hash, full_name, is_superuser) "
                "VALUES (:o,:u,:p,:n,:su) RETURNING id"
            ),
            {"o": principal.org_id, "u": username, "p": hash_password(data.password),
             "n": data.full_name, "su": data.is_superuser},
        )
    ).scalar_one()
    await _set_roles(session, uid, data.role_ids)
    await _set_branches(session, uid, data.branch_ids)
    return await get_user(session, principal.org_id, uid)


async def update_user(
    session: AsyncSession, principal: Principal, user_id: int, data: UserUpdate
) -> dict:
    current = await get_user(session, principal.org_id, user_id)
    sent = data.model_fields_set

    is_superuser = data.is_superuser if "is_superuser" in sent else current["is_superuser"]
    is_active = data.is_active if "is_active" in sent else current["is_active"]
    role_ids = data.role_ids if data.role_ids is not None else list(current["role_ids"])
    branch_ids = data.branch_ids if data.branch_ids is not None else list(current["branch_ids"])

    # Locking yourself out is a one-way trip that needs DB access to undo.
    if user_id == principal.user_id:
        if not is_active:
            raise ValueError("You cannot deactivate your own account")
        if current["is_superuser"] and not is_superuser:
            raise ValueError("You cannot remove your own super user rights")
    if current["is_superuser"] and (not is_superuser or not is_active):
        others = (
            await session.execute(
                text(
                    "SELECT count(*) FROM app_user "
                    "WHERE org_id=:o AND id<>:i AND is_superuser AND is_active"
                ),
                {"o": principal.org_id, "i": user_id},
            )
        ).scalar_one()
        if not others:
            raise ValueError("This is the last active super user — promote another one first")

    await _validate_access(session, principal.org_id, role_ids, branch_ids, is_superuser)

    if "full_name" in sent or "is_superuser" in sent or "is_active" in sent:
        await session.execute(
            text(
                "UPDATE app_user SET full_name=:n, is_superuser=:su, is_active=:ia "
                "WHERE org_id=:o AND id=:i"
            ),
            {"n": data.full_name if "full_name" in sent else current["full_name"],
             "su": is_superuser, "ia": is_active, "o": principal.org_id, "i": user_id},
        )
    if data.role_ids is not None:
        await _set_roles(session, user_id, role_ids)
    if data.branch_ids is not None:
        await _set_branches(session, user_id, branch_ids)
    return await get_user(session, principal.org_id, user_id)


async def reset_password(
    session: AsyncSession, principal: Principal, user_id: int, password: str
) -> dict:
    await get_user(session, principal.org_id, user_id)  # 404s if not in this org
    await session.execute(
        text("UPDATE app_user SET password_hash=:p WHERE org_id=:o AND id=:i"),
        {"p": hash_password(password), "o": principal.org_id, "i": user_id},
    )
    return await get_user(session, principal.org_id, user_id)


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
