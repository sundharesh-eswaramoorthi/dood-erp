"""payments: cash/bank accounts, account ledger, payment vouchers

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-29
"""
from alembic import op

revision = "0014"
down_revision = "0013"
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
CREATE TABLE cash_bank_account (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    branch_id       BIGINT,
    name            TEXT NOT NULL,
    account_type    TEXT NOT NULL CHECK (account_type IN ('bank','cash','petty_cash')),
    opening_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    current_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    version         BIGINT NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

CREATE TABLE account_ledger_entry (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    account_id      BIGINT NOT NULL REFERENCES cash_bank_account(id),
    direction       TEXT NOT NULL CHECK (direction IN ('in','out')),
    amount          NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    source_doc_type TEXT NOT NULL,
    source_doc_id   BIGINT NOT NULL,
    source_line_no  INT NOT NULL DEFAULT 0,
    entry_purpose   TEXT NOT NULL DEFAULT 'original'
                     CHECK (entry_purpose IN ('original','reversal','reallocation')),
    reversal_seq    INT NOT NULL DEFAULT 0,
    effective_date  DATE NOT NULL,
    created_by      BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_account_ledger_source UNIQUE
        (org_id, source_doc_type, source_doc_id, source_line_no, entry_purpose, reversal_seq)
);
CREATE INDEX ix_ale_account ON account_ledger_entry (org_id, account_id, id);

CREATE TABLE payment_voucher (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       BIGINT NOT NULL,
    branch_id    BIGINT NOT NULL,
    party_id     BIGINT NOT NULL,
    account_id   BIGINT NOT NULL REFERENCES cash_bank_account(id),
    doc_no       TEXT,
    voucher_type TEXT NOT NULL CHECK (voucher_type IN ('receipt','payment')),
    amount       NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    voucher_date DATE NOT NULL,
    note         TEXT,
    created_by   BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_ale_immutable BEFORE UPDATE OR DELETE ON account_ledger_entry
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
"""

DROP = """
DROP TRIGGER IF EXISTS trg_ale_immutable ON account_ledger_entry;
DROP TABLE IF EXISTS payment_voucher CASCADE;
DROP TABLE IF EXISTS account_ledger_entry CASCADE;
DROP TABLE IF EXISTS cash_bank_account CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_org_rls("cash_bank_account"))
    op.execute(_org_rls("account_ledger_entry"))
    op.execute(_branch_rls("payment_voucher"))


def downgrade() -> None:
    op.execute(DROP)
