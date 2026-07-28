"""delivery — the exactly-once stock-out mover

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-29
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _branch_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {table}_rls ON {table}
    USING (
        org_id = current_setting('app.org_id', true)::bigint
        AND branch_id = ANY (string_to_array(current_setting('app.branch_ids', true), ',')::bigint[])
    )
    WITH CHECK (
        org_id = current_setting('app.org_id', true)::bigint
        AND branch_id = ANY (string_to_array(current_setting('app.branch_ids', true), ',')::bigint[])
    );
"""


def _org_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {table}_rls ON {table}
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);
"""


SCHEMA = """
CREATE TABLE delivery (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    branch_id       BIGINT NOT NULL,
    sale_order_id   BIGINT NOT NULL,
    doc_no          TEXT,
    delivery_date   DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','dispatched','delivered','failed','cancelled')),
    delivery_boy_id BIGINT,
    created_by      BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE delivery_line (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id             BIGINT NOT NULL,
    delivery_id        BIGINT NOT NULL REFERENCES delivery(id),
    line_no            INT NOT NULL,
    sale_order_id      BIGINT NOT NULL,
    sale_order_line_no INT NOT NULL,
    product_id         BIGINT NOT NULL,
    godown_id          BIGINT NOT NULL,
    base_qty           NUMERIC(20,6) NOT NULL CHECK (base_qty > 0),
    UNIQUE (delivery_id, line_no)
);
"""

DROP = """
DROP TABLE IF EXISTS delivery_line CASCADE;
DROP TABLE IF EXISTS delivery CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_branch_rls("delivery"))
    op.execute(_org_rls("delivery_line"))


def downgrade() -> None:
    op.execute(DROP)
