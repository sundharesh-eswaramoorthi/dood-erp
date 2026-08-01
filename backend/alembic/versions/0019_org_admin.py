"""v2 §9 "Add branch" + §2 godown management + §9 "Add documents (customisable)".

branch and godown have existed since 0001 but only seed.py ever inserted into
them — there was no way to add a second branch from the app. They also carried
no RLS, unlike every other org-scoped master, so this closes that gap too.

The branch gains the identity fields an invoice header needs (code, address,
GSTIN, state code); V2.10's printing reads them, so they land here rather than
forcing a second migration later.

document_type replaces the hard-coded party document list in the UI.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-01
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _org_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {table}_rls ON {table};
CREATE POLICY {table}_rls ON {table}
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);
"""


UP = """
ALTER TABLE branch ADD COLUMN code       TEXT;
ALTER TABLE branch ADD COLUMN address    TEXT;
ALTER TABLE branch ADD COLUMN phone      TEXT;
ALTER TABLE branch ADD COLUMN gstin      TEXT;
ALTER TABLE branch ADD COLUMN state_code TEXT;
CREATE UNIQUE INDEX uq_branch_name ON branch (org_id, lower(name));
CREATE UNIQUE INDEX uq_branch_code ON branch (org_id, lower(code)) WHERE code IS NOT NULL;

ALTER TABLE godown ADD COLUMN code TEXT;
CREATE UNIQUE INDEX uq_godown_name ON godown (org_id, branch_id, lower(name));

-- v2 §9: the party-document type list becomes data, not a hard-coded dropdown.
CREATE TABLE document_type (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      BIGINT NOT NULL,
    name        TEXT NOT NULL,
    applies_to  TEXT NOT NULL DEFAULT 'party'
                CHECK (applies_to IN ('party','product','branch')),
    is_required BOOLEAN NOT NULL DEFAULT false,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    sort_order  INT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX uq_document_type ON document_type (org_id, applies_to, lower(name));

-- the types the UI used to hard-code, for every org that already exists
INSERT INTO document_type (org_id, name, applies_to, sort_order)
SELECT o.id, t.name, 'party', t.ord
FROM organization o
CROSS JOIN (VALUES ('GST Certificate', 1), ('PAN Card', 2), ('KYC', 3), ('Other', 4))
     AS t(name, ord);
"""

DOWN = """
DROP TABLE IF EXISTS document_type CASCADE;
DROP INDEX IF EXISTS uq_godown_name;
ALTER TABLE godown DROP COLUMN IF EXISTS code;
DROP INDEX IF EXISTS uq_branch_code;
DROP INDEX IF EXISTS uq_branch_name;
ALTER TABLE branch DROP COLUMN IF EXISTS state_code;
ALTER TABLE branch DROP COLUMN IF EXISTS gstin;
ALTER TABLE branch DROP COLUMN IF EXISTS phone;
ALTER TABLE branch DROP COLUMN IF EXISTS address;
ALTER TABLE branch DROP COLUMN IF EXISTS code;
ALTER TABLE branch DISABLE ROW LEVEL SECURITY;
ALTER TABLE godown DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS branch_rls ON branch;
DROP POLICY IF EXISTS godown_rls ON godown;
"""


def upgrade() -> None:
    op.execute(UP)
    # bring these two in line with every other org-scoped master
    op.execute(_org_rls("branch"))
    op.execute(_org_rls("godown"))
    op.execute(_org_rls("document_type"))


def downgrade() -> None:
    op.execute(DOWN)
