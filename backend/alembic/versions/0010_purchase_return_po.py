"""purchase returns (reverse goods + payable) and optional purchase orders

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-29
"""
from alembic import op

revision = "0010"
down_revision = "0009"
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
CREATE TABLE purchase_return (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        BIGINT NOT NULL,
    branch_id     BIGINT NOT NULL,
    supplier_id   BIGINT NOT NULL,
    godown_id     BIGINT NOT NULL,
    doc_no        TEXT,
    orig_bill_id  BIGINT,
    supply_type   TEXT NOT NULL DEFAULT 'intra' CHECK (supply_type IN ('intra','inter')),
    return_date   DATE NOT NULL,
    status        TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('draft','posted','cancelled')),
    taxable_total NUMERIC(14,2) NOT NULL DEFAULT 0,
    tax_total     NUMERIC(14,2) NOT NULL DEFAULT 0,
    grand_total   NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_by    BIGINT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE purchase_return_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    return_id       BIGINT NOT NULL REFERENCES purchase_return(id),
    line_no         INT NOT NULL,
    product_id      BIGINT NOT NULL,
    entered_qty     NUMERIC(20,6) NOT NULL,
    entered_unit_id BIGINT NOT NULL,
    base_qty        NUMERIC(20,6) NOT NULL CHECK (base_qty > 0),
    rate            NUMERIC(18,4) NOT NULL,
    taxable         NUMERIC(14,2) NOT NULL,
    gst_rate        NUMERIC(5,2) NOT NULL DEFAULT 0,
    cgst            NUMERIC(14,2) NOT NULL DEFAULT 0,
    sgst            NUMERIC(14,2) NOT NULL DEFAULT 0,
    igst            NUMERIC(14,2) NOT NULL DEFAULT 0,
    line_total      NUMERIC(14,2) NOT NULL,
    UNIQUE (return_id, line_no)
);

-- Optional Purchase Order (non-posting; gated by the purchase_order feature flag)
CREATE TABLE purchase_order (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        BIGINT NOT NULL,
    branch_id     BIGINT NOT NULL,
    supplier_id   BIGINT NOT NULL,
    doc_no        TEXT,
    order_date    DATE NOT NULL,
    expected_date DATE,
    status        TEXT NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open','approved','closed','cancelled')),
    note          TEXT,
    created_by    BIGINT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE purchase_order_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    po_id           BIGINT NOT NULL REFERENCES purchase_order(id),
    line_no         INT NOT NULL,
    product_id      BIGINT NOT NULL,
    entered_qty     NUMERIC(20,6) NOT NULL,
    entered_unit_id BIGINT NOT NULL,
    rate            NUMERIC(18,4) NOT NULL DEFAULT 0,
    UNIQUE (po_id, line_no)
);
"""

DROP = """
DROP TABLE IF EXISTS purchase_order_line CASCADE;
DROP TABLE IF EXISTS purchase_order CASCADE;
DROP TABLE IF EXISTS purchase_return_line CASCADE;
DROP TABLE IF EXISTS purchase_return CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_branch_rls("purchase_return"))
    op.execute(_org_rls("purchase_return_line"))
    op.execute(_branch_rls("purchase_order"))
    op.execute(_org_rls("purchase_order_line"))


def downgrade() -> None:
    op.execute(DROP)
