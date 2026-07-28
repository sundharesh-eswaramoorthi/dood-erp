"""settings: tax rates, tags, system settings / feature flags

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _org_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {table}_rls ON {table}
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);
"""


SCHEMA = """
CREATE TABLE tax_rate (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id    BIGINT NOT NULL,
    name      TEXT NOT NULL,
    rate      NUMERIC(5,2) NOT NULL CHECK (rate >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

CREATE TABLE tag_definition (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id    BIGINT NOT NULL,
    name      TEXT NOT NULL,
    color     TEXT NOT NULL DEFAULT '#B96D28',
    is_active BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

CREATE TABLE tag_assignment (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      BIGINT NOT NULL,
    tag_id      BIGINT NOT NULL REFERENCES tag_definition(id),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('party','product')),
    entity_id   BIGINT NOT NULL,
    UNIQUE (org_id, tag_id, entity_type, entity_id)
);

CREATE TABLE system_setting (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    key        TEXT NOT NULL,
    value      JSONB NOT NULL DEFAULT '{}'::jsonb,
    scope      TEXT NOT NULL DEFAULT 'org',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, key)
);
"""

TABLES = ["tax_rate", "tag_definition", "tag_assignment", "system_setting"]

DROP = """
DROP TABLE IF EXISTS system_setting CASCADE;
DROP TABLE IF EXISTS tag_assignment CASCADE;
DROP TABLE IF EXISTS tag_definition CASCADE;
DROP TABLE IF EXISTS tax_rate CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in TABLES:
        op.execute(_org_rls(t))


def downgrade() -> None:
    op.execute(DROP)
