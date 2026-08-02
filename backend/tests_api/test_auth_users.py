"""Auth, users, roles and permissions over HTTP.

The service tests cannot reach any of this: they construct a Principal by hand,
so the token, the permission decorator and the 401/403 split have never been
exercised end to end.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from .conftest import login, uniq

pytestmark = pytest.mark.asyncio


# ---- health / root --------------------------------------------------------
async def test_health_endpoints_need_no_token(client):
    for url in ("/healthz", "/readyz", "/"):
        r = await client.get(url)
        assert r.status_code == 200, f"{url} -> {r.status_code}"


# ---- login ----------------------------------------------------------------
async def test_login_returns_a_usable_token(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"].lower() == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["username"] == "admin"
    assert body["user"]["branch_ids"] and body["user"]["perms"]


async def test_login_rejects_a_bad_password(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


async def test_login_rejects_an_unknown_user(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "nobody", "password": "x"})
    assert r.status_code == 401


async def test_refresh_exchanges_for_a_new_access_token(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "admin", "password": "admin123"})
    refresh = r.json()["refresh_token"]
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200, r2.text
    assert r2.json()["access_token"]


async def test_refresh_refuses_an_access_token(client):
    """The two token types are not interchangeable; using an access token to
    refresh would let a leaked short-lived token be renewed for ever."""
    r = await client.post("/api/v1/auth/login",
                          data={"username": "admin", "password": "admin123"})
    access = r.json()["access_token"]
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r2.status_code == 401


# ---- who am I -------------------------------------------------------------
async def test_me_describes_the_caller(client, admin):
    r = await client.get("/api/v1/auth/me", headers=admin)
    assert r.status_code == 200
    me = r.json()
    assert me["user_id"] and me["org_id"]
    assert me["branch_ids"], "the seeded admin must work in at least one branch"
    assert me["perms"], "the seeded admin must carry permissions"


async def test_no_token_is_401_not_403(client):
    """A missing token and a forbidden action are different answers; conflating
    them sends the UI to the wrong place."""
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_a_garbage_token_is_401(client):
    r = await client.get("/api/v1/auth/me",
                         headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


# ---- roles & permissions catalogue ---------------------------------------
async def test_roles_and_permissions_are_listed(client, admin):
    roles = await client.get("/api/v1/roles", headers=admin)
    assert roles.status_code == 200
    codes = {r["code"] for r in roles.json()}
    # v2.8 renamed the v1 roles IN PLACE (role.id preserved) and added
    # purchase_executive, so user_role assignments survived the rename
    assert {"super_admin", "branch_manager", "sales_executive",
            "purchase_executive", "store_keeper", "delivery_staff"} <= codes

    perms = await client.get("/api/v1/permissions", headers=admin)
    assert perms.status_code == 200
    codes = {p["code"] for p in perms.json()}
    # v2.8 raised the catalogue to 27 codes across the three edit rights
    assert {"invoice.edit.today", "invoice.edit.backdated", "invoice.cancel"} <= codes


# ---- users ----------------------------------------------------------------
async def test_users_can_be_listed(client, admin):
    r = await client.get("/api/v1/users", headers=admin)
    assert r.status_code == 200
    assert any(u["username"] == "admin" for u in r.json())


async def test_create_user_edit_and_reset_password(client, admin, base):
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    salesman = next(r for r in roles if r["code"] == "sales_executive")
    username = uniq("user")

    created = await client.post("/api/v1/users", headers=admin, json={
        "username": username, "password": "secret123", "full_name": "Test User",
        "role_ids": [salesman["id"]], "branch_ids": [base["branch"]],
    })
    assert created.status_code in (200, 201), created.text
    uid = created.json()["id"]

    # the new user can log in and sees exactly their own role's permissions
    token = await login(client, username, "secret123")
    me = (await client.get("/api/v1/auth/me",
                           headers={"Authorization": f"Bearer {token}"})).json()
    assert me["user_id"] == uid
    assert "*" not in me["perms"], "a salesman must not hold the wildcard"

    # edit
    edited = await client.put(f"/api/v1/users/{uid}", headers=admin,
                              json={"full_name": "Renamed"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["full_name"] == "Renamed"

    # password reset, and the new password is the one that works
    reset = await client.post(f"/api/v1/users/{uid}/password", headers=admin,
                              json={"password": "brandnew456"})
    assert reset.status_code in (200, 204), reset.text
    assert await login(client, username, "brandnew456")
    bad = await client.post("/api/v1/auth/login",
                            data={"username": username, "password": "secret123"})
    assert bad.status_code == 401, "the old password must stop working"


async def test_a_user_cannot_be_created_without_a_role_or_branch(client, admin, base):
    """V2.11: both were creatable as empty, and the result was a user who got
    403 everywhere or a dashboard that 400d — broken accounts that looked fine."""
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    no_role = await client.post("/api/v1/users", headers=admin, json={
        "username": uniq("norole"), "password": "secret123",
        "role_ids": [], "branch_ids": [base["branch"]],
    })
    assert no_role.status_code == 422, no_role.text

    no_branch = await client.post("/api/v1/users", headers=admin, json={
        "username": uniq("nobranch"), "password": "secret123",
        "role_ids": [roles[0]["id"]], "branch_ids": [],
    })
    assert no_branch.status_code == 422, no_branch.text


async def test_a_duplicate_username_is_refused(client, admin, base):
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    name = uniq("dupe")
    payload = {"username": name, "password": "secret123",
               "role_ids": [roles[0]["id"]], "branch_ids": [base["branch"]]}
    first = await client.post("/api/v1/users", headers=admin, json=payload)
    assert first.status_code in (200, 201)
    second = await client.post("/api/v1/users", headers=admin, json=payload)
    assert second.status_code in (409, 422), second.text


async def test_a_short_password_is_refused_as_structured_json(client, admin, base):
    """The white-screen bug: FastAPI answers a schema rejection with an ARRAY of
    {loc,msg}. The page put that straight into a component and React unmounted
    the whole app. The shape is asserted here so the client can rely on it."""
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    r = await client.post("/api/v1/users", headers=admin, json={
        "username": uniq("shortpw"), "password": "ab",
        "role_ids": [roles[0]["id"]], "branch_ids": [base["branch"]],
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and "msg" in detail[0]


# ---- RBAC actually bites --------------------------------------------------
@pytest_asyncio.fixture
async def salesman_headers(client, admin, base) -> dict:
    """A real non-privileged login, so 403 is proven rather than assumed."""
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    role = next(r for r in roles if r["code"] == "sales_executive")
    username = uniq("sales")
    r = await client.post("/api/v1/users", headers=admin, json={
        "username": username, "password": "secret123",
        "role_ids": [role["id"]], "branch_ids": [base["branch"]],
    })
    assert r.status_code in (200, 201), r.text
    token = await login(client, username, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def test_a_salesman_may_read_parties_but_not_manage_users(client, salesman_headers):
    ok = await client.get("/api/v1/parties", headers=salesman_headers)
    assert ok.status_code == 200

    denied = await client.get("/api/v1/users", headers=salesman_headers)
    assert denied.status_code == 403, "settings.manage must be required to list users"


async def test_a_salesman_cannot_create_a_branch(client, salesman_headers):
    r = await client.post("/api/v1/branches", headers=salesman_headers,
                          json={"name": uniq("Sneaky")})
    assert r.status_code == 403
