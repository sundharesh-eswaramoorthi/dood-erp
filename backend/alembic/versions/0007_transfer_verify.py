"""stock transfers (dispatch/receive) and physical verification

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-29
"""
from alembic import op

revision = "0007"
down_revision = "0006"
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
CREATE TABLE stock_transfer (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id         BIGINT NOT NULL,
    doc_no         TEXT,
    from_branch_id BIGINT NOT NULL,
    from_godown_id BIGINT NOT NULL,
    to_branch_id   BIGINT NOT NULL,
    to_godown_id   BIGINT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','dispatched','received','cancelled')),
    dispatch_date  DATE,
    receive_date   DATE,
    created_by     BIGINT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_godown_id <> to_godown_id)
);

CREATE TABLE stock_transfer_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    transfer_id     BIGINT NOT NULL REFERENCES stock_transfer(id),
    line_no         INT NOT NULL,
    product_id      BIGINT NOT NULL,
    entered_qty     NUMERIC(20,6) NOT NULL,
    entered_unit_id BIGINT NOT NULL,
    base_qty        NUMERIC(20,6) NOT NULL CHECK (base_qty > 0),
    unit_cost       NUMERIC(18,6),
    UNIQUE (transfer_id, line_no)
);

CREATE TABLE stock_verification (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT NOT NULL,
    godown_id  BIGINT NOT NULL,
    doc_no     TEXT,
    status     TEXT NOT NULL DEFAULT 'counting'
                CHECK (status IN ('counting','posted','cancelled')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at  TIMESTAMPTZ,
    created_by BIGINT NOT NULL
);

CREATE TABLE stock_verification_line (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id              BIGINT NOT NULL,
    verification_id     BIGINT NOT NULL REFERENCES stock_verification(id),
    line_no             INT NOT NULL,
    product_id          BIGINT NOT NULL,
    system_qty_at_start NUMERIC(20,6) NOT NULL,
    physical_qty        NUMERIC(20,6),
    UNIQUE (verification_id, line_no)
);
"""

DROP = """
DROP TABLE IF EXISTS stock_verification_line CASCADE;
DROP TABLE IF EXISTS stock_verification CASCADE;
DROP TABLE IF EXISTS stock_transfer_line CASCADE;
DROP TABLE IF EXISTS stock_transfer CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_org_rls("stock_transfer"))
    op.execute(_org_rls("stock_transfer_line"))
    op.execute(_branch_rls("stock_verification"))
    op.execute(_org_rls("stock_verification_line"))


def downgrade() -> None:
    op.execute(DROP)
