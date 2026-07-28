from fastapi import APIRouter
from sqlalchemy import text

from app.core.cache import redis_client
from app.core.db import engine

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    checks = {"postgres": False, "redis": False}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        checks["redis"] = bool(await redis_client.ping())
    except Exception:  # noqa: BLE001
        pass
    ready = all(checks.values())
    return {"ready": ready, "checks": checks}
