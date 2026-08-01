"""v2 §7 requires "edit current date invoice" / "edit previous date invoice",
but no posted document could be edited at all — every module was post-only.

Editing a posted document cannot mean UPDATE: the ledgers are append-only and
the stock has already moved. So an amendment supersedes: the original is
reversed in full and a fresh revision is posted, linked both ways. Cancelling
is the same thing without the new revision.

document_amendment records who did it and why — the audit trail the role matrix
implies.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-01
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

DOCS = ("purchase_bill", "purchase_return", "sales_bill", "sales_return")

UP = """
CREATE TABLE document_amendment (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      BIGINT NOT NULL,
    branch_id   BIGINT NOT NULL,
    doc_type    TEXT NOT NULL,
    doc_id      BIGINT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('cancel','amend')),
    replaced_by BIGINT,
    reason      TEXT,
    doc_date    DATE NOT NULL,
    created_by  BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_amendment_doc ON document_amendment (org_id, doc_type, doc_id);
"""

DOWN = """
DROP TABLE IF EXISTS document_amendment CASCADE;
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
        op.execute(
            f"""
            ALTER TABLE {doc} ADD COLUMN revision_no   INT NOT NULL DEFAULT 1;
            ALTER TABLE {doc} ADD COLUMN amended_from  BIGINT;
            ALTER TABLE {doc} ADD COLUMN superseded_by BIGINT;
            ALTER TABLE {doc} ADD COLUMN cancelled_at  TIMESTAMPTZ;
            ALTER TABLE {doc} ADD COLUMN cancelled_by  BIGINT;
            ALTER TABLE {doc} ADD COLUMN cancel_reason TEXT;
            """
        )
    op.execute(_org_rls("document_amendment"))


def downgrade() -> None:
    for doc in DOCS:
        for col in ("revision_no", "amended_from", "superseded_by",
                    "cancelled_at", "cancelled_by", "cancel_reason"):
            op.execute(f"ALTER TABLE {doc} DROP COLUMN IF EXISTS {col};")
    op.execute(DOWN)
