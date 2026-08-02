"""V2.12 masters: drop party type, add the map link, number products.

party_type (customer/supplier/both) never reached the posting engine — nothing
branched on it, it only narrowed a list filter — and in this business a party
buys and sells freely, so the classification created work without buying
anything. Dropped outright rather than left to rot as a dead column.

party_address already carried lat/lng/place_id but no URL, so a pasted Google
Maps link had nowhere to live; map_link holds it verbatim and the lat/lng stay
for anything that wants coordinates.

The product series makes `code` optional the same way a party code already is:
allocated from numbering_series, gap-free, under the same row lock. It is
created for whatever financial years the org already numbers parties in, so an
org mid-year gets a matching series rather than one starting next April.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-02
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE party DROP COLUMN IF EXISTS party_type;

ALTER TABLE party_address ADD COLUMN map_link TEXT;

-- opening stock always belonged to a (branch, godown) pair — stock_balance is
-- keyed on both — but only the godown was remembered, so the form could not
-- show back which branch the opening landed in.
ALTER TABLE product ADD COLUMN opening_branch_id BIGINT;
UPDATE product p SET opening_branch_id = g.branch_id
FROM godown g WHERE g.id = p.opening_godown_id AND p.opening_godown_id IS NOT NULL;

INSERT INTO numbering_series (org_id, branch_id, doc_type, fin_year, prefix, pad_width)
SELECT org_id, NULL::bigint, 'product', fin_year, 'PRD-', 4
FROM numbering_series
WHERE doc_type = 'party'
ON CONFLICT (org_id, COALESCE(branch_id, 0), doc_type, fin_year) DO NOTHING;
"""

DOWN = """
DELETE FROM numbering_series WHERE doc_type = 'product';

ALTER TABLE product DROP COLUMN IF EXISTS opening_branch_id;

ALTER TABLE party_address DROP COLUMN IF EXISTS map_link;

-- restored as it was: NOT NULL with the original default
ALTER TABLE party ADD COLUMN party_type TEXT NOT NULL DEFAULT 'customer';
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
