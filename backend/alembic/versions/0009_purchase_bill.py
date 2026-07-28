"""purchase bills (goods-in + GST + supplier payable)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29
"""
from alembic import op

revision = "0009"
down_revision = "0008"
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
CREATE TABLE purchase_bill (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id              BIGINT NOT NULL,
    branch_id           BIGINT NOT NULL,
    supplier_id         BIGINT NOT NULL,
    godown_id           BIGINT NOT NULL,
    doc_no              TEXT,
    supplier_invoice_no TEXT,
    supply_type         TEXT NOT NULL DEFAULT 'intra' CHECK (supply_type IN ('intra','inter')),
    bill_date           DATE NOT NULL,
    status              TEXT NOT NULL DEFAULT 'posted'
                         CHECK (status IN ('draft','posted','cancelled')),
    taxable_total       NUMERIC(14,2) NOT NULL DEFAULT 0,
    tax_total           NUMERIC(14,2) NOT NULL DEFAULT 0,
    grand_total         NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_by          BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE purchase_bill_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    bill_id         BIGINT NOT NULL REFERENCES purchase_bill(id),
    line_no         INT NOT NULL,
    product_id      BIGINT NOT NULL,
    entered_qty     NUMERIC(20,6) NOT NULL,
    entered_unit_id BIGINT NOT NULL,
    base_qty        NUMERIC(20,6) NOT NULL CHECK (base_qty > 0),
    rate            NUMERIC(18,4) NOT NULL,       -- price per entered unit (ex-tax)
    taxable         NUMERIC(14,2) NOT NULL,
    gst_rate        NUMERIC(5,2) NOT NULL DEFAULT 0,
    cgst            NUMERIC(14,2) NOT NULL DEFAULT 0,
    sgst            NUMERIC(14,2) NOT NULL DEFAULT 0,
    igst            NUMERIC(14,2) NOT NULL DEFAULT 0,
    line_total      NUMERIC(14,2) NOT NULL,
    UNIQUE (bill_id, line_no)
);
"""

DROP = """
DROP TABLE IF EXISTS purchase_bill_line CASCADE;
DROP TABLE IF EXISTS purchase_bill CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_branch_rls("purchase_bill"))
    op.execute(_org_rls("purchase_bill_line"))


def downgrade() -> None:
    op.execute(DROP)
