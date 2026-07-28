"""Outbox drainer: the queue side of the transactional-outbox pattern.

Runs on a Celery beat tick, claims pending outbox rows with
`FOR UPDATE SKIP LOCKED`, and fans each event out to its projections:
  * MongoDB  -> append-only `audit_events` (the NoSQL home, plan §4)
  * Redis    -> capped `recent_activity` list + a counter (the cache)

Uses a synchronous engine/clients because Celery workers are synchronous.
"""
from __future__ import annotations

import datetime as dt
import json

import pymongo
import redis
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.workers.celery_app import celery

_engine = create_engine(settings.sync_database_url, pool_pre_ping=True, future=True)
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
_mongo = pymongo.MongoClient(settings.MONGO_URL)[settings.MONGO_DB]


def _handle(org_id: int, topic: str, payload: dict) -> None:
    at = dt.datetime.now(dt.timezone.utc).isoformat()
    # 1) MongoDB audit / activity store (outbox-projected, never diverges).
    _mongo.audit_events.insert_one(
        {"org_id": org_id, "topic": topic, "payload": payload, "at": at}
    )
    # 2) Redis recent-activity cache (capped) + activity counter.
    key = f"recent_activity:{org_id}"
    _redis.lpush(key, json.dumps({"topic": topic, "payload": payload, "at": at}))
    _redis.ltrim(key, 0, 49)
    _redis.incr(f"activity_count:{org_id}")


@celery.task(name="app.workers.tasks.drain_outbox")
def drain_outbox() -> int:
    processed = 0
    with _engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, org_id, topic, payload
                FROM outbox_event
                WHERE status = 'pending' AND available_at <= now()
                ORDER BY id
                LIMIT 100
                FOR UPDATE SKIP LOCKED
                """
            )
        ).mappings().all()
        for r in rows:
            payload = r["payload"]
            if isinstance(payload, str):  # driver-dependent; normalize to dict
                payload = json.loads(payload)
            _handle(r["org_id"], r["topic"], payload)
            conn.execute(
                text("UPDATE outbox_event SET status='done', attempts=attempts+1 WHERE id=:id"),
                {"id": r["id"]},
            )
            processed += 1
    return processed
