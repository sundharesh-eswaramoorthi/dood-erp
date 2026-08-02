"""API regression harness — the real app, over HTTP, against a real database.

This is a different instrument from tests/. Those call services directly as the
database OWNER, which deliberately puts RLS out of the way so the ledger
invariants can be driven hard. Everything between the request and the service
is therefore untested by them: routing, auth, the permission decorators, RLS as
the app role actually experiences it, request validation, status codes, and the
Decimal-to-JSON serialisation that has now bitten this project twice.

So: a dedicated database (`cholavin_apitest`), migrated and seeded exactly the
way a fresh install is, with the app connecting as `cholavin_app` — NOSUPERUSER,
so a policy that is wrong fails here the way it would in production.

The whole suite shares one database and one login. Tests must therefore not
assume an empty table; they assert about the rows they created, by id or doc_no.
"""
from __future__ import annotations

import os
import subprocess
import uuid

import psycopg2
import pytest
import pytest_asyncio

TEST_DB = "cholavin_apitest"
TEST_REDIS_DB = 15

from app.core.config import settings  # noqa: E402

_CREDS = f"{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}"
_APP_CREDS = f"{settings.APP_DB_USER}:{settings.APP_DB_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}"
SYNC_URL = f"postgresql+psycopg2://{_CREDS}/{TEST_DB}"
# the app role, NOT the owner — RLS must apply exactly as it does in production
ASYNC_URL = f"postgresql+asyncpg://{_APP_CREDS}/{TEST_DB}"
REDIS_URL = settings.REDIS_URL.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"

# `settings` is a module-level singleton built at first import, and tests/
# imports it before this file is even read — so an env var set here would be
# too late and the suite would quietly run against the DEV database. Nothing is
# left to import order: the session dependency and the Redis handle are
# redirected explicitly below.


def _admin():
    return psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD, dbname="postgres",
    )


@pytest.fixture(scope="session", autouse=True)
def api_db():
    """A throwaway database, migrated and seeded like a fresh install."""
    conn = _admin(); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    cur.execute(f"CREATE DATABASE {TEST_DB}")
    cur.close(); conn.close()

    env = {**os.environ, "ALEMBIC_URL": SYNC_URL, "POSTGRES_DB": TEST_DB,
           "REDIS_URL": REDIS_URL}
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd="/app", env=env)
    # the real seed, so the suite tests what a real install actually contains
    subprocess.run(["python", "-m", "app.seed"], check=True, cwd="/app", env=env)

    yield

    conn = _admin(); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    cur.close(); conn.close()


# Every (METHOD, route-template) the suite actually reached. test_zz_coverage
# turns this into the guarantee that no endpoint went untested — a suite that
# claims to cover an API should be able to prove it rather than be believed.
COVERED: set[tuple[str, str]] = set()


class _RecordingApp:
    """Records the route FastAPI matched, which is the template (/x/{id}) and
    not the concrete URL — the app fills scope['route'] during routing, and we
    hold the same dict."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)
        route = scope.get("route")
        if route is not None and scope.get("type") == "http":
            COVERED.add((scope["method"], route.path))


@pytest_asyncio.fixture
async def client(api_db):
    """httpx bound straight to the ASGI app — no network, real middleware.

    Function-scoped on purpose: a session-scoped async fixture would need the
    event loop pinned to the session too, and the client itself is nearly free
    to build (ASGITransport, no sockets). The expensive setup — migrate, seed,
    build reference data — is cached below instead.
    """
    import httpx
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.db import get_session
    from app.main import app

    # Point the app at the TEST database by overriding the one dependency every
    # route resolves through — get_scoped_session takes get_session via Depends,
    # so both the scoped and unscoped paths follow. Doing it here rather than
    # through env vars is what makes the suite immune to import order.
    engine = create_async_engine(ASYNC_URL, poolclass=None)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _test_session():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _test_session

    # The dashboard cache and the activity feed key on org_id, which is 1 both
    # here and in a running dev stack, so they get a Redis database of their own.
    # Each consumer bound the name at import, so each is redirected.
    import app.modules.activity.router as activity_router
    import app.modules.dashboard.service as dashboard_service
    import app.modules.health.router as health_router

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    originals = {}
    for module in (activity_router, dashboard_service, health_router):
        originals[module] = module.redis_client
        module.redis_client = redis

    transport = httpx.ASGITransport(app=_RecordingApp(app))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        for module, original in originals.items():
            module.redis_client = original
        app.dependency_overrides.pop(get_session, None)
        # Connections are bound to this test's event loop; one reused after the
        # loop closes raises "Event loop is closed" in the NEXT test.
        await redis.aclose()
        await engine.dispose()


async def login(client, username: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"login failed for {username}: {r.status_code} {r.text}"
    return r.json()["access_token"]


_CACHE: dict = {}


@pytest_asyncio.fixture
async def admin(client) -> dict:
    """Authorization header for the seeded super user, logged in once."""
    if "admin" not in _CACHE:
        token = await login(client, settings.SEED_ADMIN_USERNAME, settings.SEED_ADMIN_PASSWORD)
        _CACHE["admin"] = {"Authorization": f"Bearer {token}"}
    return _CACHE["admin"]


@pytest.fixture
def idem() -> dict:
    """A fresh Idempotency-Key. Posting endpoints replay on a repeated key, so
    reusing one across tests silently returns the previous document."""
    return {"Idempotency-Key": str(uuid.uuid4())}


def uniq(prefix: str) -> str:
    """Unique name — the suite shares one database and most masters are
    unique-per-org, so fixed literals collide the second time a test runs."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---- shared reference data ------------------------------------------------
# Built once and reused. Creating a party/product per test would work but would
# make a 100-endpoint suite crawl, and would obscure which endpoint broke.


@pytest_asyncio.fixture
async def base(client, admin) -> dict:
    """The org's existing shape plus one customer, one supplier and one product
    with stock — enough for every document endpoint to have something to act on.

    Built once and cached: a party and product per test would work, but would
    make a 118-endpoint suite crawl and would blur which endpoint actually broke.
    """
    if "base" in _CACHE:
        return _CACHE["base"]

    async def get(url):
        r = await client.get(url, headers=admin)
        assert r.status_code == 200, f"GET {url} -> {r.status_code} {r.text}"
        return r.json()

    me = await get("/api/v1/auth/me")
    branches = await get("/api/v1/branches")
    godowns = await get("/api/v1/godowns")
    units = await get("/api/v1/units")
    accounts = await get("/api/v1/accounts/bank-accounts")
    ptypes = await get("/api/v1/accounts/payment-types")

    # Branches are org-VISIBLE but documents may only be filed against a branch
    # the caller works in, so pick from the principal — taking branches[0] picks
    # up whatever another test happened to create.
    mine = set(me["branch_ids"])
    branch = next(b["id"] for b in branches if b["id"] in mine)
    godown = next(g["id"] for g in godowns if g["branch_id"] == branch)
    unit = units[0]["id"]

    async def post(url, payload, **kw):
        r = await client.post(url, json=payload, headers={**admin, **kw.pop("headers", {})})
        assert r.status_code in (200, 201), f"POST {url} -> {r.status_code} {r.text}"
        return r.json()

    customer = await post("/api/v1/parties", {
        "name": uniq("Customer"), "area": "Central", "serving_branch_id": branch,
        "phone": "9000000001",
    }, headers={"Idempotency-Key": str(uuid.uuid4())})
    supplier = await post("/api/v1/parties", {
        "name": uniq("Supplier"), "area": "Central", "serving_branch_id": branch,
        "phone": "9000000002",
    }, headers={"Idempotency-Key": str(uuid.uuid4())})

    product = await post("/api/v1/products", {
        "name": uniq("Rice"), "base_unit_id": unit, "gst_rate": "5",
        "sale_price": "100", "purchase_price": "60", "hsn_code": "1006",
    })

    # stock to sell: an opening adjustment through the real posting path
    await post("/api/v1/stock/adjustments", {
        "branch_id": branch, "godown_id": godown, "adj_reason": "opening",
        "lines": [{"product_id": product["id"], "entered_qty": "1000",
                   "entered_unit_id": unit, "unit_cost": "50"}],
    }, headers={"Idempotency-Key": str(uuid.uuid4())})

    _CACHE["base"] = {
        "me": me, "branch": branch, "godown": godown,
        "godown2": next(
            (g["id"] for g in godowns if g["branch_id"] == branch and g["id"] != godown),
            godown,
        ),
        "unit": unit, "customer": customer["id"], "supplier": supplier["id"],
        "product": product["id"],
        "account": accounts[0]["id"] if accounts else None,
        "payment_type": ptypes[0]["id"] if ptypes else None,
    }
    return _CACHE["base"]
