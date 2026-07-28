"""Transactional outbox — write side effects in the SAME transaction as the
mutation. The Celery drainer (app.workers.tasks.drain_outbox) delivers them
post-commit, so projections (Mongo audit, Redis activity cache) can never
diverge from the committed write.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def emit(session: AsyncSession, org_id: int, topic: str, payload: dict) -> None:
    await session.execute(
        text(
            "INSERT INTO outbox_event (org_id, topic, payload) "
            "VALUES (:o, :t, CAST(:p AS jsonb))"
        ),
        {"o": org_id, "t": topic, "p": json.dumps(payload)},
    )
