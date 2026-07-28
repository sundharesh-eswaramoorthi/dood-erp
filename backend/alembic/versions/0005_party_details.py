"""full party: contacts, addresses (geo), documents, GST registrations

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


# Party children are branch-scoped like their parent (org + branch RLS), so a
# child can never leak across branches even if a party_id from another branch
# is guessed.
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


SCHEMA = """
ALTER TABLE party ADD COLUMN pan TEXT;
ALTER TABLE party ADD COLUMN credit_limit NUMERIC(14,2);

CREATE TABLE party_contact (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      BIGINT NOT NULL,
    branch_id   BIGINT NOT NULL,
    party_id    BIGINT NOT NULL REFERENCES party(id),
    name        TEXT NOT NULL,
    phone       TEXT,
    email       TEXT,
    designation TEXT,
    is_primary  BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX ix_party_contact ON party_contact (org_id, party_id);

CREATE TABLE party_address (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT NOT NULL,
    party_id   BIGINT NOT NULL REFERENCES party(id),
    label      TEXT,
    line1      TEXT NOT NULL,
    line2      TEXT,
    city       TEXT,
    state      TEXT,
    pincode    TEXT,
    lat        NUMERIC(10,7),
    lng        NUMERIC(10,7),
    place_id   TEXT,
    is_default BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX ix_party_address ON party_address (org_id, party_id);

CREATE TABLE party_document (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       BIGINT NOT NULL,
    branch_id    BIGINT NOT NULL,
    party_id     BIGINT NOT NULL REFERENCES party(id),
    doc_type     TEXT NOT NULL,
    file_name    TEXT NOT NULL,
    storage_key  TEXT NOT NULL,
    content_type TEXT,
    uploaded_by  BIGINT NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_party_document ON party_document (org_id, party_id);

CREATE TABLE party_gst_registration (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT NOT NULL,
    party_id   BIGINT NOT NULL REFERENCES party(id),
    gstin      TEXT NOT NULL,
    state_code TEXT,
    legal_name TEXT,
    is_default BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (org_id, gstin)
);
CREATE INDEX ix_party_gst ON party_gst_registration (org_id, party_id);
"""

TABLES = ["party_contact", "party_address", "party_document", "party_gst_registration"]

DROP = """
DROP TABLE IF EXISTS party_gst_registration CASCADE;
DROP TABLE IF EXISTS party_document CASCADE;
DROP TABLE IF EXISTS party_address CASCADE;
DROP TABLE IF EXISTS party_contact CASCADE;
ALTER TABLE party DROP COLUMN IF EXISTS credit_limit;
ALTER TABLE party DROP COLUMN IF EXISTS pan;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in TABLES:
        op.execute(_branch_rls(t))


def downgrade() -> None:
    op.execute(DROP)
