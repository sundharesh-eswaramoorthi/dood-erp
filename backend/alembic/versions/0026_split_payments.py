"""V2.14 split payments: one document, several tenders.

Every money-taking document carried a single paid_amount and a single
payment_account_id, so "₹2000 cash and ₹3000 by UPI" could not be recorded at
all — the operator had to pick one and misstate the other. document_payment is
the line item that was missing.

Each split names BOTH where the money landed (cash_bank_account) and how it was
taken (payment_type). Those are different questions: two cards and a UPI may
all settle into the same bank account, and §6 wants sales broken down by mode.

The ledgers need no change. Both key on source_line_no, so a split posts as
(<doc>_payment, doc_id, seq) and the existing reversal — which already loops
every row and preserves the line number — negates all of them unaided.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-02
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE document_payment (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          BIGINT NOT NULL,
    branch_id       BIGINT NOT NULL,
    -- sales_bill | purchase_bill | sales_return | purchase_return | payment_voucher
    doc_type        TEXT   NOT NULL,
    doc_id          BIGINT NOT NULL,
    -- 0-based, and reused verbatim as source_line_no in both ledgers so a
    -- split's party entry and account entry line up with each other
    seq             INT    NOT NULL,
    account_id      BIGINT NOT NULL REFERENCES cash_bank_account(id),
    payment_type_id BIGINT REFERENCES payment_type(id),
    amount          NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    reference       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_payment UNIQUE (org_id, doc_type, doc_id, seq)
);
CREATE INDEX ix_document_payment_doc ON document_payment (org_id, doc_type, doc_id);
CREATE INDEX ix_document_payment_type ON document_payment (org_id, payment_type_id);

ALTER TABLE document_payment ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_payment FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS document_payment_rls ON document_payment;
CREATE POLICY document_payment_rls ON document_payment
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);

-- Backfill: every payment taken so far was a single tender, so it becomes
-- seq 0 pointing at the account the document already named. Without this the
-- payment-mode reports would show all history as "no split recorded".
INSERT INTO document_payment (org_id, branch_id, doc_type, doc_id, seq, account_id, amount)
SELECT b.org_id, b.branch_id, 'sales_bill', b.id, 0, e.account_id, b.paid_amount
FROM sales_bill b
JOIN account_ledger_entry e
  ON e.org_id = b.org_id AND e.source_doc_type = 'sales_bill_payment'
 AND e.source_doc_id = b.id AND e.entry_purpose = 'original'
WHERE b.paid_amount > 0
ON CONFLICT DO NOTHING;

INSERT INTO document_payment (org_id, branch_id, doc_type, doc_id, seq, account_id, amount)
SELECT b.org_id, b.branch_id, 'purchase_bill', b.id, 0, e.account_id, b.paid_amount
FROM purchase_bill b
JOIN account_ledger_entry e
  ON e.org_id = b.org_id AND e.source_doc_type = 'purchase_bill_payment'
 AND e.source_doc_id = b.id AND e.entry_purpose = 'original'
WHERE b.paid_amount > 0
ON CONFLICT DO NOTHING;

INSERT INTO document_payment (org_id, branch_id, doc_type, doc_id, seq, account_id,
                              payment_type_id, amount)
SELECT v.org_id, v.branch_id, 'payment_voucher', v.id, 0, v.account_id,
       v.payment_type_id, v.amount
FROM payment_voucher v
ON CONFLICT DO NOTHING;
"""

DOWN = """
DROP TABLE IF EXISTS document_payment;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
