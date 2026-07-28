"""Reads the Redis recent-activity cache that the Celery outbox drainer writes.

This closes the end-to-end loop: a scoped write -> outbox row (Postgres) ->
Celery drainer -> Redis cache + Mongo audit -> this read. Proving the whole
pipeline is wired.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from app.core.cache import redis_client
from app.core.deps import Principal, get_principal

router = APIRouter()


@router.get("")
async def recent(principal: Principal = Depends(get_principal)):
    key = f"recent_activity:{principal.org_id}"
    raw = await redis_client.lrange(key, 0, 19)
    count = await redis_client.get(f"activity_count:{principal.org_id}")
    return {
        "count": int(count) if count else 0,
        "items": [json.loads(item) for item in raw],
    }
