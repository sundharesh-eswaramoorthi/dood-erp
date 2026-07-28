"""Gap-free document numbering — Postgres-only allocator (plan §5.7 / Phase-2 §8.2).

The counter is advanced under a row lock inside the caller's transaction, so
concurrent posts serialize and no number is ever gapped or duplicated. Redis is
never consulted here.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def current_fin_year(on: dt.date | None = None) -> str:
    d = on or dt.date.today()
    start = d.year if d.month >= 4 else d.year - 1  # India FY starts April
    return f"FY{start}-{str(start + 1)[-2:]}"


async def allocate(
    session: AsyncSession,
    org_id: int,
    branch_id: int | None,
    doc_type: str,
    fin_year: str | None = None,
) -> str:
    fy = fin_year or current_fin_year()
    row = (
        await session.execute(
            text(
                """
                SELECT id, prefix, pad_width, next_value
                FROM numbering_series
                WHERE org_id = :o
                  AND COALESCE(branch_id, 0) = COALESCE(:b, 0)
                  AND doc_type = :d
                  AND fin_year = :fy
                FOR UPDATE
                """
            ),
            {"o": org_id, "b": branch_id, "d": doc_type, "fy": fy},
        )
    ).mappings().first()
    if row is None:
        raise ValueError(f"No numbering series for doc_type={doc_type} fin_year={fy}")

    n = row["next_value"]
    await session.execute(
        text("UPDATE numbering_series SET next_value = next_value + 1 WHERE id = :id"),
        {"id": row["id"]},
    )
    return f'{row["prefix"]}{str(n).zfill(row["pad_width"])}'
