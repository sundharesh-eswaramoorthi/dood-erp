"""stock ledger core: movement ledger, balances, WAC cost, reservations,
fulfillment, reorder thresholds, adjustments; append-only trigger

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29
"""
from alembic import op

revision = "0006"
down_revision = "0005"
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
-- The inventory truth: append-only, signed base-unit rows.
CREATE TABLE stock_movement_ledger (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id            BIGINT NOT NULL,
    branch_id         BIGINT NOT NULL,
    godown_id         BIGINT NOT NULL,
    product_id        BIGINT NOT NULL,
    signed_qty        NUMERIC(20,6) NOT NULL CHECK (signed_qty <> 0),
    unit_cost         NUMERIC(18,6),
    movement_type     TEXT NOT NULL CHECK (movement_type IN
                        ('purchase','sale','transfer_out','transfer_in',
                         'adjustment','return_in','return_out','opening','verification')),
    location_state    TEXT NOT NULL DEFAULT 'on_hand'
                        CHECK (location_state IN ('on_hand','in_transit')),
    source_doc_type   TEXT NOT NULL,
    source_doc_id     BIGINT NOT NULL,
    source_line_no    INT NOT NULL,
    entry_purpose     TEXT NOT NULL DEFAULT 'original'
                        CHECK (entry_purpose IN ('original','reversal','reallocation')),
    reversal_seq      INT NOT NULL DEFAULT 0,
    reverses_entry_id BIGINT REFERENCES stock_movement_ledger(id),
    effective_date    DATE NOT NULL,
    created_by        BIGINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_stock_ledger_source UNIQUE
        (org_id, source_doc_type, source_doc_id, source_line_no, entry_purpose, reversal_seq)
);
CREATE INDEX ix_sml_balance ON stock_movement_ledger
    (org_id, product_id, branch_id, godown_id, location_state);
CREATE INDEX ix_sml_replay ON stock_movement_ledger
    (org_id, product_id, branch_id, effective_date, id);

-- Materialized balance: a hot, transactionally-maintained cache of SUM(ledger).
CREATE TABLE stock_balance (
    org_id         BIGINT NOT NULL,
    branch_id      BIGINT NOT NULL,
    godown_id      BIGINT NOT NULL,
    product_id     BIGINT NOT NULL,
    location_state TEXT NOT NULL DEFAULT 'on_hand',
    on_hand        NUMERIC(20,6) NOT NULL DEFAULT 0,
    reserved       NUMERIC(20,6) NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    version        BIGINT NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, product_id, branch_id, godown_id, location_state)
);

-- Moving weighted-average cost, scope per (product, branch).
CREATE TABLE product_cost (
    org_id          BIGINT NOT NULL,
    branch_id       BIGINT NOT NULL,
    product_id      BIGINT NOT NULL,
    moving_avg_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
    qty_basis       NUMERIC(20,6) NOT NULL DEFAULT 0,
    version         BIGINT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, product_id, branch_id)
);

CREATE TABLE stock_reservation (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id               BIGINT NOT NULL,
    branch_id            BIGINT NOT NULL,
    godown_id            BIGINT NOT NULL,
    product_id           BIGINT NOT NULL,
    qty                  NUMERIC(20,6) NOT NULL CHECK (qty > 0),
    status               TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','released','expired')),
    source_order_id      BIGINT NOT NULL,
    source_order_line_no INT NOT NULL,
    expires_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at          TIMESTAMPTZ
);
CREATE INDEX ix_resv_active ON stock_reservation (org_id, product_id, branch_id, godown_id)
    WHERE status = 'active';

CREATE TABLE stock_fulfillment (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id             BIGINT NOT NULL,
    branch_id          BIGINT NOT NULL,
    sale_order_id      BIGINT NOT NULL,
    sale_order_line_no INT NOT NULL,
    moved_qty          NUMERIC(20,6) NOT NULL CHECK (moved_qty > 0),
    moved_by_doc_type  TEXT NOT NULL CHECK (moved_by_doc_type IN ('delivery','sales_bill')),
    moved_by_doc_id    BIGINT NOT NULL,
    godown_id          BIGINT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_fulfil_line ON stock_fulfillment (org_id, sale_order_id, sale_order_line_no);

CREATE TABLE reorder_threshold (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    godown_id  BIGINT,
    min_qty    NUMERIC(20,6) NOT NULL CHECK (min_qty >= 0)
);
CREATE UNIQUE INDEX uq_reorder ON reorder_threshold
    (org_id, product_id, branch_id, COALESCE(godown_id, 0));

CREATE TABLE stock_adjustment (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id         BIGINT NOT NULL,
    branch_id      BIGINT NOT NULL,
    godown_id      BIGINT NOT NULL,
    doc_no         TEXT,
    adj_reason     TEXT NOT NULL CHECK (adj_reason IN
                    ('increase','decrease','damage','shortage','opening')),
    status         TEXT NOT NULL DEFAULT 'posted'
                    CHECK (status IN ('draft','posted','cancelled')),
    effective_date DATE NOT NULL,
    note           TEXT,
    created_by     BIGINT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stock_adjustment_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    adjustment_id   BIGINT NOT NULL REFERENCES stock_adjustment(id),
    line_no         INT NOT NULL,
    product_id      BIGINT NOT NULL,
    entered_qty     NUMERIC(20,6) NOT NULL,
    entered_unit_id BIGINT NOT NULL,
    base_qty        NUMERIC(20,6) NOT NULL,
    unit_cost       NUMERIC(18,6),
    UNIQUE (adjustment_id, line_no)
);

-- The ledger is append-only, enforced by the database itself.
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'ledger is append-only'; END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sml_immutable BEFORE UPDATE OR DELETE ON stock_movement_ledger
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
"""

BRANCH_TABLES = [
    "stock_movement_ledger", "stock_balance", "product_cost",
    "stock_reservation", "stock_fulfillment", "reorder_threshold", "stock_adjustment",
]
ORG_TABLES = ["stock_adjustment_line"]

DROP = """
DROP TRIGGER IF EXISTS trg_sml_immutable ON stock_movement_ledger;
DROP FUNCTION IF EXISTS forbid_mutation();
DROP TABLE IF EXISTS stock_adjustment_line CASCADE;
DROP TABLE IF EXISTS stock_adjustment CASCADE;
DROP TABLE IF EXISTS reorder_threshold CASCADE;
DROP TABLE IF EXISTS stock_fulfillment CASCADE;
DROP TABLE IF EXISTS stock_reservation CASCADE;
DROP TABLE IF EXISTS product_cost CASCADE;
DROP TABLE IF EXISTS stock_balance CASCADE;
DROP TABLE IF EXISTS stock_movement_ledger CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in BRANCH_TABLES:
        op.execute(_branch_rls(t))
    for t in ORG_TABLES:
        op.execute(_org_rls(t))


def downgrade() -> None:
    op.execute(DROP)
