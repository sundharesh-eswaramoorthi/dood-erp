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
# The reconciler runs system-wide across all orgs, so it connects as the owner
# (bypasses RLS) rather than the branch-scoped app role.
_owner_engine = create_engine(settings.migration_database_url, pool_pre_ping=True, future=True)
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


_STOCK_DRIFT = """
SELECT count(*) FROM stock_balance b
LEFT JOIN (SELECT org_id,product_id,branch_id,godown_id,location_state,SUM(signed_qty) s
           FROM stock_movement_ledger GROUP BY 1,2,3,4,5) l
  ON l.org_id=b.org_id AND l.product_id=b.product_id AND l.branch_id=b.branch_id
     AND l.godown_id=b.godown_id AND l.location_state=b.location_state
WHERE b.on_hand <> COALESCE(l.s,0)
"""
_RESERVED_DRIFT = """
SELECT count(*) FROM stock_balance b
LEFT JOIN (SELECT org_id,product_id,branch_id,godown_id,SUM(qty) s
           FROM stock_reservation WHERE status='active' GROUP BY 1,2,3,4) r
  ON r.org_id=b.org_id AND r.product_id=b.product_id AND r.branch_id=b.branch_id AND r.godown_id=b.godown_id
WHERE b.reserved <> COALESCE(r.s,0)
"""
_PARTY_DRIFT = """
SELECT count(*) FROM party_balance p
LEFT JOIN (SELECT org_id,party_id,
                  SUM(CASE entry_side WHEN 'debit' THEN amount ELSE -amount END) s
           FROM party_ledger_entry GROUP BY 1,2) e
  ON e.org_id=p.org_id AND e.party_id=p.party_id
WHERE p.net_balance <> COALESCE(e.s,0)
"""


@celery.task(name="app.workers.tasks.nightly_reconcile")
def nightly_reconcile() -> dict:
    """Prove every materialized balance still equals its ledger. Any non-zero is a bug."""
    with _owner_engine.connect() as conn:
        stock = conn.execute(text(_STOCK_DRIFT)).scalar_one()
        reserved = conn.execute(text(_RESERVED_DRIFT)).scalar_one()
        party = conn.execute(text(_PARTY_DRIFT)).scalar_one()
    result = {"stock_drift": stock, "reserved_drift": reserved, "party_drift": party,
              "ok": (stock == 0 and reserved == 0 and party == 0)}
    _redis.set("reconcile:last", str(result))
    if not result["ok"]:
        print(f"[reconcile] DRIFT DETECTED: {result}")
    return result


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
