"""v2 §3 "Payment type (add payment type)" + "Payment history", and finally
wiring ledger_allocation.

ledger_allocation has existed since 0008 with ZERO code references. It is what
turns "this party owes 50,000" into "against which bills" — the data behind
v2 §3's payment history on an invoice and v2 §6's outstanding/ageing reports.

payment_type is the user-definable list a payment is taken by (Cash, UPI, Card,
Cheque, ...). It is deliberately separate from cash_bank_account: the account
says WHERE the money landed, the type says HOW it was taken, and v2 §6 wants
"Payment Mode-wise Sales" off the latter.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-01
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

DOCS = ("purchase_bill", "purchase_return", "sales_bill", "sales_return")

UP = """
CREATE TABLE payment_type (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id             BIGINT NOT NULL,
    name               TEXT NOT NULL,
    kind               TEXT NOT NULL DEFAULT 'other'
                       CHECK (kind IN ('cash','bank','card','upi','cheque','credit','other')),
    default_account_id BIGINT,
    is_active          BOOLEAN NOT NULL DEFAULT true,
    sort_order         INT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX uq_payment_type ON payment_type (org_id, lower(name));

INSERT INTO payment_type (org_id, name, kind, sort_order)
SELECT o.id, t.name, t.kind, t.ord
FROM organization o
CROSS JOIN (VALUES
    ('Cash', 'cash', 1), ('UPI', 'upi', 2), ('Card', 'card', 3),
    ('Cheque', 'cheque', 4), ('Bank Transfer', 'bank', 5), ('Credit', 'credit', 6)
) AS t(name, kind, ord);

ALTER TABLE payment_voucher ADD COLUMN payment_type_id BIGINT REFERENCES payment_type(id);

-- ledger_allocation is queried both ways: "what settled this invoice" and
-- "what did this receipt pay off".
CREATE INDEX ix_alloc_against ON ledger_allocation (org_id, against_entry_id);
CREATE INDEX ix_alloc_settle  ON ledger_allocation (org_id, settle_entry_id);
"""

DOWN = """
DROP INDEX IF EXISTS ix_alloc_settle;
DROP INDEX IF EXISTS ix_alloc_against;
ALTER TABLE payment_voucher DROP COLUMN IF EXISTS payment_type_id;
DROP TABLE IF EXISTS payment_type CASCADE;
"""


def _org_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {table}_rls ON {table};
CREATE POLICY {table}_rls ON {table}
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);
"""


def upgrade() -> None:
    op.execute(UP)
    for doc in DOCS:
        op.execute(f"ALTER TABLE {doc} ADD COLUMN payment_type_id BIGINT REFERENCES payment_type(id);")
    op.execute(_org_rls("payment_type"))


def downgrade() -> None:
    for doc in DOCS:
        op.execute(f"ALTER TABLE {doc} DROP COLUMN IF EXISTS payment_type_id;")
    op.execute(DOWN)
