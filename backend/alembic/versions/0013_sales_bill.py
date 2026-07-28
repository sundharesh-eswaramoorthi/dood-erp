"""sales bills (receivable + COGS; stock only if not delivered) and sales returns

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-29
"""
from alembic import op

revision = "0013"
down_revision = "0012"
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
CREATE TABLE sales_bill (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        BIGINT NOT NULL,
    branch_id     BIGINT NOT NULL,
    customer_id   BIGINT NOT NULL,
    sale_order_id BIGINT,
    doc_no        TEXT,
    supply_type   TEXT NOT NULL DEFAULT 'intra' CHECK (supply_type IN ('intra','inter')),
    bill_date     DATE NOT NULL,
    status        TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('draft','posted','cancelled')),
    taxable_total NUMERIC(14,2) NOT NULL DEFAULT 0,
    tax_total     NUMERIC(14,2) NOT NULL DEFAULT 0,
    cogs_total    NUMERIC(14,2) NOT NULL DEFAULT 0,
    grand_total   NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_by    BIGINT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales_bill_line (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       BIGINT NOT NULL,
    bill_id      BIGINT NOT NULL REFERENCES sales_bill(id),
    line_no      INT NOT NULL,
    product_id   BIGINT NOT NULL,
    base_qty     NUMERIC(20,6) NOT NULL,
    moved_qty    NUMERIC(20,6) NOT NULL DEFAULT 0,   -- stock the BILL moved (0 if delivery did)
    rate         NUMERIC(18,4) NOT NULL,
    taxable      NUMERIC(14,2) NOT NULL,
    gst_rate     NUMERIC(5,2) NOT NULL DEFAULT 0,
    cgst         NUMERIC(14,2) NOT NULL DEFAULT 0,
    sgst         NUMERIC(14,2) NOT NULL DEFAULT 0,
    igst         NUMERIC(14,2) NOT NULL DEFAULT 0,
    cogs_amount  NUMERIC(14,2) NOT NULL DEFAULT 0,
    line_total   NUMERIC(14,2) NOT NULL,
    UNIQUE (bill_id, line_no)
);

CREATE TABLE sales_return (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        BIGINT NOT NULL,
    branch_id     BIGINT NOT NULL,
    customer_id   BIGINT NOT NULL,
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

CREATE TABLE sales_return_line (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    return_id       BIGINT NOT NULL REFERENCES sales_return(id),
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
"""

DROP = """
DROP TABLE IF EXISTS sales_return_line CASCADE;
DROP TABLE IF EXISTS sales_return CASCADE;
DROP TABLE IF EXISTS sales_bill_line CASCADE;
DROP TABLE IF EXISTS sales_bill CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_branch_rls("sales_bill"))
    op.execute(_org_rls("sales_bill_line"))
    op.execute(_branch_rls("sales_return"))
    op.execute(_org_rls("sales_return_line"))


def downgrade() -> None:
    op.execute(DROP)
