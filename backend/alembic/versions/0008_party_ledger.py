"""party ledger: entries, balances, allocations, journal vouchers

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-29
"""
from alembic import op

revision = "0008"
down_revision = "0007"
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
-- The receivable/payable truth: append-only debit/credit rows.
CREATE TABLE party_ledger_entry (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id              BIGINT NOT NULL,
    branch_id           BIGINT NOT NULL,
    party_id            BIGINT NOT NULL,
    gst_registration_id BIGINT,
    entry_side          TEXT NOT NULL CHECK (entry_side IN ('debit','credit')),
    amount              NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    source_doc_type     TEXT NOT NULL,
    source_doc_id       BIGINT NOT NULL,
    source_line_no      INT NOT NULL DEFAULT 0,
    entry_purpose       TEXT NOT NULL DEFAULT 'original'
                         CHECK (entry_purpose IN ('original','reversal','reallocation')),
    reversal_seq        INT NOT NULL DEFAULT 0,
    effective_date      DATE NOT NULL,
    created_by          BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_party_ledger_source UNIQUE
        (org_id, source_doc_type, source_doc_id, source_line_no, entry_purpose, reversal_seq)
);
CREATE INDEX ix_ple_party ON party_ledger_entry (org_id, party_id, effective_date, id);

-- Materialized balance: net = SUM(debit) - SUM(credit); + receivable / - payable.
CREATE TABLE party_balance (
    org_id      BIGINT NOT NULL,
    party_id    BIGINT NOT NULL,
    net_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    receivable  NUMERIC(14,2) NOT NULL DEFAULT 0,
    payable     NUMERIC(14,2) NOT NULL DEFAULT 0,
    version     BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, party_id)
);

CREATE TABLE ledger_allocation (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id           BIGINT NOT NULL,
    party_id         BIGINT NOT NULL,
    settle_entry_id  BIGINT NOT NULL REFERENCES party_ledger_entry(id),
    against_entry_id BIGINT NOT NULL REFERENCES party_ledger_entry(id),
    amount           NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A minimal document to own manual ledger postings (opening balances, journal
-- adjustments). Bills/receipts in later phases post through the same primitive.
CREATE TABLE journal_voucher (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT NOT NULL,
    party_id   BIGINT NOT NULL,
    doc_no     TEXT,
    note       TEXT,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- party ledger is append-only too (reuses forbid_mutation() from 0006)
CREATE TRIGGER trg_ple_immutable BEFORE UPDATE OR DELETE ON party_ledger_entry
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
"""

DROP = """
DROP TRIGGER IF EXISTS trg_ple_immutable ON party_ledger_entry;
DROP TABLE IF EXISTS journal_voucher CASCADE;
DROP TABLE IF EXISTS ledger_allocation CASCADE;
DROP TABLE IF EXISTS party_balance CASCADE;
DROP TABLE IF EXISTS party_ledger_entry CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(_branch_rls("party_ledger_entry"))
    op.execute(_org_rls("party_balance"))
    op.execute(_org_rls("ledger_allocation"))
    op.execute(_branch_rls("journal_voucher"))


def downgrade() -> None:
    op.execute(DROP)
