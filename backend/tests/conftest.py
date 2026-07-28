"""Property-test harness.

Spins up a throwaway `cholavin_test` database, runs the real Alembic migrations
on it, and hands each test a session (as the DB owner, so RLS is out of the way)
plus a freshly-seeded org / branch / godowns / unit / product. The engine
primitives run for real; the tests then assert the ledger invariants hold after
random operation sequences.
"""
from __future__ import annotations

import os
import subprocess

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings

TEST_DB = "cholavin_test"
_CREDS = f"{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}"
ASYNC_URL = f"postgresql+asyncpg://{_CREDS}/{TEST_DB}"
SYNC_URL = f"postgresql+psycopg2://{_CREDS}/{TEST_DB}"


def _admin():
    return psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD, dbname="postgres",
    )


@pytest.fixture(scope="session")
def migrated_db():
    conn = _admin(); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    cur.execute(f"CREATE DATABASE {TEST_DB}")
    cur.close(); conn.close()

    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True, cwd="/app", env={**os.environ, "ALEMBIC_URL": SYNC_URL},
    )
    yield
    conn = _admin(); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    cur.close(); conn.close()


@pytest_asyncio.fixture
async def ctx(migrated_db):
    engine = create_async_engine(ASYNC_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        org = (await s.execute(text("INSERT INTO organization (name) VALUES ('T') RETURNING id"))).scalar_one()
        await s.execute(text("SELECT set_config('app.org_id', :o, false)"), {"o": str(org)})
        branch = (await s.execute(text("INSERT INTO branch (org_id, name) VALUES (:o,'B') RETURNING id"), {"o": org})).scalar_one()
        await s.execute(text("SELECT set_config('app.branch_ids', :b, false)"), {"b": str(branch)})
        g1 = (await s.execute(text("INSERT INTO godown (org_id, branch_id, name) VALUES (:o,:b,'G1') RETURNING id"), {"o": org, "b": branch})).scalar_one()
        g2 = (await s.execute(text("INSERT INTO godown (org_id, branch_id, name) VALUES (:o,:b,'G2') RETURNING id"), {"o": org, "b": branch})).scalar_one()
        unit = (await s.execute(text("INSERT INTO unit_of_measure (org_id, code, name) VALUES (:o,'BAG','Bag') RETURNING id"), {"o": org})).scalar_one()
        prod = (await s.execute(
            text("INSERT INTO product (org_id, code, name, base_unit_id, created_by) VALUES (:o,'P1','Test',:u,1) RETURNING id"),
            {"o": org, "u": unit},
        )).scalar_one()
        party = (await s.execute(
            text("INSERT INTO party (org_id, branch_id, party_code, name, created_by) VALUES (:o,:b,'C1','Cust',1) RETURNING id"),
            {"o": org, "b": branch},
        )).scalar_one()
        from app.services.numbering import current_fin_year
        fy = current_fin_year()
        for doc_type, prefix in [("sale_order", "SO-"), ("delivery", "DLV-"), ("sales_bill", "SB-")]:
            await s.execute(
                text("INSERT INTO numbering_series (org_id, branch_id, doc_type, fin_year, prefix, pad_width) "
                     "VALUES (:o, NULL, :d, :fy, :px, 4)"),
                {"o": org, "d": doc_type, "fy": fy, "px": prefix},
            )
        await s.commit()
        yield {"s": s, "org": org, "branch": branch, "godown": g1, "godown2": g2, "unit": unit, "product": prod, "party": party}
    await engine.dispose()
