"""V2.16: branch becomes the visibility boundary.

Nineteen tables — every document and all stock — were already branch-scoped.
Three things sat outside it and are brought in:

  party (+ its children)  V2.1 deliberately moved these to org RLS so every
                          branch saw every customer, with serving_branch_id as
                          a label. That is now reversed: the branch that serves
                          a party is the branch that can see it. A customer who
                          buys from two branches needs a record in each, with
                          separate codes, ledgers and outstanding balances —
                          the cost of the wall, accepted knowingly.

  cash_bank_account       Already had branch_id and never used it. The three
                          seeded accounts have none at all, so they are given
                          to the first branch; a branch without accounts cannot
                          take payment until one is created for it.

  godown                  Had branch_id and org-only RLS, so every branch could
                          see every store.

Products stay ORG-WIDE on purpose. One catalogue, with stock and moving-average
cost held per branch — which is what lets a stock transfer move goods from one
branch to another at all. Branch enters the picture in the stock figures, not
in the item list.

party_balance keeps org RLS: it is keyed on (org_id, party_id) with no branch
column, and is only reachable through a party that branch RLS now hides.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-02
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _branch_rls(table: str, col: str = "branch_id") -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {table}_rls ON {table};
CREATE POLICY {table}_rls ON {table}
    USING (
        org_id = current_setting('app.org_id', true)::bigint
        AND {col} = ANY (string_to_array(current_setting('app.branch_ids', true), ',')::bigint[])
    )
    WITH CHECK (
        org_id = current_setting('app.org_id', true)::bigint
        AND {col} = ANY (string_to_array(current_setting('app.branch_ids', true), ',')::bigint[])
    );
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


UP = (
    # the party itself keys on the branch that serves it
    _branch_rls("party", "serving_branch_id")
    # children carry their own branch_id, stamped from the parent at creation
    + _branch_rls("party_contact")
    + _branch_rls("party_address")
    + _branch_rls("party_document")
    + _branch_rls("party_gst_registration")
    + _branch_rls("godown")
    + """
-- A child whose parent has since moved branch would vanish; realign them all
-- before the policy starts filtering on it.
UPDATE party_contact          c SET branch_id = p.serving_branch_id FROM party p WHERE p.id = c.party_id;
UPDATE party_address          c SET branch_id = p.serving_branch_id FROM party p WHERE p.id = c.party_id;
UPDATE party_document         c SET branch_id = p.serving_branch_id FROM party p WHERE p.id = c.party_id;
UPDATE party_gst_registration c SET branch_id = p.serving_branch_id FROM party p WHERE p.id = c.party_id;

-- Accounts: give the unassigned ones to the lowest-numbered branch, then make
-- the column mandatory so a new account can never be invisible to everyone.
UPDATE cash_bank_account a
   SET branch_id = (SELECT min(id) FROM branch b WHERE b.org_id = a.org_id)
 WHERE a.branch_id IS NULL;
ALTER TABLE cash_bank_account ALTER COLUMN branch_id SET NOT NULL;
"""
    + _branch_rls("cash_bank_account")
)

DOWN = (
    _org_rls("party")
    + _org_rls("party_contact")
    + _org_rls("party_address")
    + _org_rls("party_document")
    + _org_rls("party_gst_registration")
    + _org_rls("godown")
    + _org_rls("cash_bank_account")
    + "ALTER TABLE cash_bank_account ALTER COLUMN branch_id DROP NOT NULL;\n"
)


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
