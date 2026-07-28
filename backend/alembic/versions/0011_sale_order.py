"""sale orders (pending/delivered/cancelled) with stock reservations

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-29
"""
from alembic import op

revision = "0011"
down_revision = "0010"
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
CREATE TABLE sale_order (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      BIGINT NOT NULL,
    branch_id   BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    doc_no      TEXT,
    order_date  DATE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','delivered','cancelled')),
    note        TEXT,
    created_by  BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sale_order_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    order_id        BIGINT NOT NULL REFERENCES sale_order(id),
    line_no         INT NOT NULL,
    product_id      BIGINT NOT NULL,
    godown_id       BIGINT NOT NULL,
    entered_qty     NUMERIC(20,6) NOT NULL,
    entered_unit_id BIGINT NOT NULL,
    base_qty        NUMERIC(20,6) NOT NULL CHECK (base_qty > 0),
    rate            NUMERIC(18,4) NOT NULL DEFAULT 0,
    UNIQUE (order_id, line_no)
);
"""

DROP = """
DROP TABLE IF EXISTS sale_order_line CASCADE;
DROP TABLE IF EXISTS sale_order CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_branch_rls("sale_order"))
    op.execute(_org_rls("sale_order_line"))


def downgrade() -> None:
    op.execute(DROP)
