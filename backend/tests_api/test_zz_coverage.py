"""The coverage guard.

A suite that claims to cover an API should be able to prove it rather than be
believed. Every request the suite makes records the route FastAPI matched; this
compares that against the app's own route table and fails with the list of
endpoints nobody exercised.

Named test_zz_* so it sorts last — it can only judge what has already run, and
only when the whole suite runs together.
"""
from __future__ import annotations

import pytest

from .conftest import COVERED

pytestmark = pytest.mark.asyncio

# Generated docs and the ASGI plumbing around them: served by FastAPI itself,
# nothing of ours to regress.
EXEMPT_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


def _app_routes() -> set[tuple[str, str]]:
    from app.main import app

    out = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods or route.path in EXEMPT_PATHS:
            continue
        for method in methods - {"HEAD", "OPTIONS"}:
            out.add((method, route.path))
    return out


async def test_every_endpoint_was_exercised(client, admin):
    # touch the docs-adjacent root so the app is definitely imported
    await client.get("/healthz")

    expected = _app_routes()
    missing = sorted(expected - COVERED)
    covered = expected & COVERED

    report = "\n".join(f"  {m:6} {p}" for m, p in missing)
    assert not missing, (
        f"{len(missing)} of {len(expected)} endpoints were never called by the "
        f"suite:\n{report}"
    )
    assert len(covered) == len(expected)


async def test_coverage_is_not_vacuous():
    """Guard the guard: if the recorder silently stopped working, the set would
    be empty and the comparison above would still pass on an empty expectation."""
    assert len(COVERED) > 50, f"only {len(COVERED)} routes recorded — recorder broken?"
