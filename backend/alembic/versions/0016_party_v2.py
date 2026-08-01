"""v2 §1 Parties: area, active flag, opening balance, contact relationship,
and the scope change -- parties (and their children) become ORG-wide instead of
branch-scoped, per v2 §9 "All branch parties in one place".

`party.branch_id` is renamed to `serving_branch_id`: it is no longer the RLS
boundary, it is the editable "Current Serving Branch" attribute from v2 §1.
Party children keep their branch_id column (harmless provenance) but their RLS
drops to org-only so they stay visible wherever the parent is.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-01
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

CHILDREN = ("party_contact", "party_address", "party_document", "party_gst_registration")


def _org_rls(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS {table}_rls ON {table};
CREATE POLICY {table}_rls ON {table}
    USING (org_id = current_setting('app.org_id', true)::bigint)
    WITH CHECK (org_id = current_setting('app.org_id', true)::bigint);
"""


def _branch_rls(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS {table}_rls ON {table};
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


UP = """
-- v2 §1 fields. area is "required" in the spec but legacy rows predate it, so
-- it is NOT NULL DEFAULT '' at the DB and enforced non-empty by the API.
ALTER TABLE party ADD COLUMN area                 TEXT NOT NULL DEFAULT '';
ALTER TABLE party ADD COLUMN is_active            BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE party ADD COLUMN opening_balance      NUMERIC(14,2) NOT NULL DEFAULT 0
                                                  CHECK (opening_balance >= 0);
ALTER TABLE party ADD COLUMN opening_balance_side TEXT NOT NULL DEFAULT 'receivable'
                                                  CHECK (opening_balance_side IN ('receivable','payable'));
ALTER TABLE party ADD COLUMN opening_as_of        DATE;

-- "Add another contact with relationship field" (v2 §1). designation stays for
-- the B2B job-title case; relationship is the v2 field.
ALTER TABLE party_contact ADD COLUMN relationship TEXT;

-- The party is now org-wide; branch_id becomes the editable serving branch.
DROP POLICY IF EXISTS party_rls ON party;
ALTER TABLE party RENAME COLUMN branch_id TO serving_branch_id;
ALTER INDEX ix_party_scope RENAME TO ix_party_serving_branch;
CREATE INDEX ix_party_area ON party (org_id, lower(area));
"""

DOWN = """
DROP INDEX IF EXISTS ix_party_area;
ALTER INDEX ix_party_serving_branch RENAME TO ix_party_scope;
DROP POLICY IF EXISTS party_rls ON party;
ALTER TABLE party RENAME COLUMN serving_branch_id TO branch_id;
ALTER TABLE party_contact DROP COLUMN relationship;
ALTER TABLE party DROP COLUMN opening_as_of;
ALTER TABLE party DROP COLUMN opening_balance_side;
ALTER TABLE party DROP COLUMN opening_balance;
ALTER TABLE party DROP COLUMN is_active;
ALTER TABLE party DROP COLUMN area;
"""


def upgrade() -> None:
    op.execute(UP)
    op.execute(_org_rls("party"))
    for t in CHILDREN:
        op.execute(_org_rls(t))


def downgrade() -> None:
    op.execute(DOWN)
    op.execute(_branch_rls("party"))
    for t in CHILDREN:
        op.execute(_branch_rls(t))
