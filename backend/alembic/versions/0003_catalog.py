"""catalog: units, conversions, categories, products, packings

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-29
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# Org-scoped masters (shared across branches). RLS keyed on org_id only; the
# app.org_id GUC is set per request in app.core.deps.get_scoped_session.
def _org_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {table}_rls ON {table}
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);
"""


SCHEMA = """
CREATE TABLE unit_of_measure (
    id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id BIGINT NOT NULL,
    code   TEXT NOT NULL,
    name   TEXT NOT NULL,
    UNIQUE (org_id, code)
);

CREATE TABLE product_category (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id    BIGINT NOT NULL,
    name      TEXT NOT NULL,
    parent_id BIGINT REFERENCES product_category(id),
    is_active BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

CREATE TABLE product (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id               BIGINT NOT NULL,
    code                 TEXT NOT NULL,
    name                 TEXT NOT NULL,
    category_id          BIGINT REFERENCES product_category(id),
    base_unit_id         BIGINT NOT NULL REFERENCES unit_of_measure(id),
    allow_negative_stock BOOLEAN NOT NULL DEFAULT false,
    reorder_default      NUMERIC(20,6),
    hsn_code             TEXT,
    gst_rate             NUMERIC(5,2),
    is_active            BOOLEAN NOT NULL DEFAULT true,
    created_by           BIGINT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, code)
);
CREATE INDEX ix_product_name ON product (org_id, lower(name));

-- Per-product unit conversions to the base unit (immutable once referenced).
CREATE TABLE unit_conversion (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id         BIGINT NOT NULL,
    product_id     BIGINT NOT NULL REFERENCES product(id),
    from_unit_id   BIGINT NOT NULL REFERENCES unit_of_measure(id),
    factor_to_base NUMERIC(20,8) NOT NULL CHECK (factor_to_base > 0),
    effective_from DATE NOT NULL DEFAULT DATE '0001-01-01',
    UNIQUE (org_id, product_id, from_unit_id, effective_from)
);

CREATE TABLE product_packing (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      BIGINT NOT NULL,
    product_id  BIGINT NOT NULL REFERENCES product(id),
    unit_id     BIGINT NOT NULL REFERENCES unit_of_measure(id),
    qty_in_base NUMERIC(20,6) NOT NULL CHECK (qty_in_base > 0),
    label       TEXT
);
"""

TABLES = ["unit_of_measure", "product_category", "product", "unit_conversion", "product_packing"]

DROP = """
DROP TABLE IF EXISTS product_packing CASCADE;
DROP TABLE IF EXISTS unit_conversion CASCADE;
DROP TABLE IF EXISTS product CASCADE;
DROP TABLE IF EXISTS product_category CASCADE;
DROP TABLE IF EXISTS unit_of_measure CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in TABLES:
        op.execute(_org_rls(t))


def downgrade() -> None:
    op.execute(DROP)
