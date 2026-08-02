"""User administration guards (V2.11).

Creating a user used to succeed in states that produced a broken login — no
branch (empty app, dashboard 400) or no role (403 everywhere) — and an unknown
role id surfaced as a 500 from the foreign key. These pin the guards down.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.deps import Principal
from app.core.security import verify_password
from app.modules.users import service
from app.modules.users.schemas import UserCreate, UserUpdate


async def _role(ctx, code: str) -> int:
    return (
        await ctx["s"].execute(
            text("INSERT INTO role (org_id, code, name) VALUES (:o,:c,:n) RETURNING id"),
            {"o": ctx["org"], "c": code, "n": code.replace("_", " ").title()},
        )
    ).scalar_one()


def _principal(ctx, user_id: int = 1) -> Principal:
    return Principal(user_id=user_id, org_id=ctx["org"], branch_ids=[ctx["branch"]], perms={"*"})


async def test_create_rejects_unknown_ids(ctx):
    p = _principal(ctx)
    with pytest.raises(ValueError, match="Unknown role"):
        await service.create_user(
            ctx["s"], p, UserCreate(username="u1", password="pw1234", role_ids=[999_999],
                                    branch_ids=[ctx["branch"]]),
        )
    with pytest.raises(ValueError, match="Unknown branch"):
        await service.create_user(
            ctx["s"], p, UserCreate(username="u1", password="pw1234", role_ids=[],
                                    branch_ids=[999_999], is_superuser=True),
        )


async def test_create_requires_branch_and_role(ctx):
    p = _principal(ctx)
    role = await _role(ctx, "clerk")
    with pytest.raises(ValueError, match="at least one branch"):
        await service.create_user(
            ctx["s"], p, UserCreate(username="u2", password="pw1234", role_ids=[role], branch_ids=[]),
        )
    with pytest.raises(ValueError, match="at least one role"):
        await service.create_user(
            ctx["s"], p, UserCreate(username="u2", password="pw1234", role_ids=[],
                                    branch_ids=[ctx["branch"]]),
        )
    # a super user carries every permission, so it needs no role
    su = await service.create_user(
        ctx["s"], p, UserCreate(username="u2", password="pw1234", role_ids=[],
                                branch_ids=[ctx["branch"]], is_superuser=True),
    )
    assert su["is_superuser"] and su["branch_ids"] == [ctx["branch"]]


async def test_username_is_case_insensitive(ctx):
    p = _principal(ctx)
    role = await _role(ctx, "clerk")
    await service.create_user(
        ctx["s"], p, UserCreate(username="Ravi", password="pw1234", role_ids=[role],
                                branch_ids=[ctx["branch"]]),
    )
    with pytest.raises(ValueError, match="is taken"):
        await service.create_user(
            ctx["s"], p, UserCreate(username="RAVI", password="pw1234", role_ids=[role],
                                    branch_ids=[ctx["branch"]]),
        )


async def test_update_replaces_roles_and_branches(ctx):
    p = _principal(ctx)
    r1, r2 = await _role(ctx, "clerk"), await _role(ctx, "manager")
    b2 = (
        await ctx["s"].execute(
            text("INSERT INTO branch (org_id, name) VALUES (:o,'B2') RETURNING id"), {"o": ctx["org"]}
        )
    ).scalar_one()

    u = await service.create_user(
        ctx["s"], p, UserCreate(username="u3", password="pw1234", role_ids=[r1],
                                branch_ids=[ctx["branch"]]),
    )
    out = await service.update_user(
        ctx["s"], p, u["id"], UserUpdate(role_ids=[r2], branch_ids=[ctx["branch"], b2]),
    )
    assert out["role_ids"] == [r2]
    assert sorted(out["branch_ids"]) == sorted([ctx["branch"], b2])

    # omitting a list leaves it alone; sending [] would strand the account
    out = await service.update_user(ctx["s"], p, u["id"], UserUpdate(full_name="Renamed"))
    assert out["full_name"] == "Renamed" and out["role_ids"] == [r2]
    with pytest.raises(ValueError, match="at least one branch"):
        await service.update_user(ctx["s"], p, u["id"], UserUpdate(branch_ids=[]))


async def test_cannot_lock_yourself_out(ctx):
    p = _principal(ctx)
    role = await _role(ctx, "clerk")
    u = await service.create_user(
        ctx["s"], p, UserCreate(username="u4", password="pw1234", role_ids=[role],
                                branch_ids=[ctx["branch"]], is_superuser=True),
    )
    me = _principal(ctx, user_id=u["id"])
    with pytest.raises(ValueError, match="your own account"):
        await service.update_user(ctx["s"], me, u["id"], UserUpdate(is_active=False))
    with pytest.raises(ValueError, match="your own super user"):
        await service.update_user(ctx["s"], me, u["id"], UserUpdate(is_superuser=False))

    # nor may somebody else, while this is the only super user left
    with pytest.raises(ValueError, match="last active super user"):
        await service.update_user(ctx["s"], p, u["id"], UserUpdate(is_active=False))

    # once a second one exists, disabling the first is fine
    await service.create_user(
        ctx["s"], p, UserCreate(username="u4b", password="pw1234", role_ids=[],
                                branch_ids=[ctx["branch"]], is_superuser=True),
    )
    out = await service.update_user(ctx["s"], p, u["id"], UserUpdate(is_active=False))
    assert out["is_active"] is False


async def test_password_reset_changes_the_hash(ctx):
    p = _principal(ctx)
    role = await _role(ctx, "clerk")
    u = await service.create_user(
        ctx["s"], p, UserCreate(username="u5", password="pw1234", role_ids=[role],
                                branch_ids=[ctx["branch"]]),
    )
    await service.reset_password(ctx["s"], p, u["id"], "newpw123")
    stored = (
        await ctx["s"].execute(text("SELECT password_hash FROM app_user WHERE id=:i"), {"i": u["id"]})
    ).scalar_one()
    assert verify_password("newpw123", stored)
    assert not verify_password("pw1234", stored)
