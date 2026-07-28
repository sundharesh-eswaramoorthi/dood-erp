"""initial phase-0 schema

Revision ID: 0001
Revises:
Create Date: 2026-07-29
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA = """
CREATE TABLE organization (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE branch (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id    BIGINT NOT NULL REFERENCES organization(id),
    name      TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE godown (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id    BIGINT NOT NULL REFERENCES organization(id),
    branch_id BIGINT NOT NULL REFERENCES branch(id),
    name      TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE app_user (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        BIGINT NOT NULL REFERENCES organization(id),
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT true,
    is_superuser  BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE permission (
    code        TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE role (
    id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id BIGINT NOT NULL REFERENCES organization(id),
    code   TEXT NOT NULL,
    name   TEXT NOT NULL,
    UNIQUE (org_id, code)
);

CREATE TABLE role_permission (
    role_id         BIGINT NOT NULL REFERENCES role(id),
    permission_code TEXT   NOT NULL REFERENCES permission(code),
    PRIMARY KEY (role_id, permission_code)
);

CREATE TABLE user_role (
    user_id BIGINT NOT NULL REFERENCES app_user(id),
    role_id BIGINT NOT NULL REFERENCES role(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE user_branch_access (
    user_id   BIGINT NOT NULL REFERENCES app_user(id),
    branch_id BIGINT NOT NULL REFERENCES branch(id),
    PRIMARY KEY (user_id, branch_id)
);

CREATE TABLE numbering_series (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT,
    doc_type   TEXT NOT NULL,
    fin_year   TEXT NOT NULL,
    prefix     TEXT NOT NULL DEFAULT '',
    pad_width  SMALLINT NOT NULL DEFAULT 4,
    next_value BIGINT NOT NULL DEFAULT 1 CHECK (next_value >= 1)
);
CREATE UNIQUE INDEX uq_numbering_series
    ON numbering_series (org_id, COALESCE(branch_id, 0), doc_type, fin_year);

CREATE TABLE outbox_event (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       BIGINT NOT NULL,
    topic        TEXT NOT NULL,
    payload      JSONB NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','processing','done','failed')),
    attempts     INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_outbox_pending ON outbox_event (available_at) WHERE status = 'pending';

CREATE TABLE idempotency_key (
    org_id            BIGINT NOT NULL,
    key               TEXT NOT NULL,
    request_hash      TEXT NOT NULL,
    response_doc_type TEXT,
    response_doc_id   BIGINT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, key)
);

CREATE TABLE party (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     BIGINT NOT NULL,
    branch_id  BIGINT NOT NULL,
    party_code TEXT NOT NULL,
    name       TEXT NOT NULL,
    party_type TEXT NOT NULL DEFAULT 'customer'
               CHECK (party_type IN ('customer','supplier','both')),
    gstin      TEXT,
    phone      TEXT,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_party_scope ON party (org_id, branch_id);
CREATE INDEX ix_party_name  ON party (org_id, lower(name));

-- Row-level security: a tenant/branch-scoped table. FORCE so even the table
-- owner (the app's DB role) is subject to the policy. GUCs are set per request
-- in app.core.deps.get_scoped_session.
ALTER TABLE party ENABLE ROW LEVEL SECURITY;
ALTER TABLE party FORCE ROW LEVEL SECURITY;
CREATE POLICY party_rls ON party
    USING (
        org_id = current_setting('app.org_id', true)::bigint
        AND branch_id = ANY (string_to_array(current_setting('app.branch_ids', true), ',')::bigint[])
    )
    WITH CHECK (
        org_id = current_setting('app.org_id', true)::bigint
        AND branch_id = ANY (string_to_array(current_setting('app.branch_ids', true), ',')::bigint[])
    );
"""

DROP = """
DROP TABLE IF EXISTS party CASCADE;
DROP TABLE IF EXISTS idempotency_key CASCADE;
DROP TABLE IF EXISTS outbox_event CASCADE;
DROP TABLE IF EXISTS numbering_series CASCADE;
DROP TABLE IF EXISTS user_branch_access CASCADE;
DROP TABLE IF EXISTS user_role CASCADE;
DROP TABLE IF EXISTS role_permission CASCADE;
DROP TABLE IF EXISTS role CASCADE;
DROP TABLE IF EXISTS permission CASCADE;
DROP TABLE IF EXISTS app_user CASCADE;
DROP TABLE IF EXISTS godown CASCADE;
DROP TABLE IF EXISTS branch CASCADE;
DROP TABLE IF EXISTS organization CASCADE;
"""


def upgrade() -> None:
    op.execute(SCHEMA)


def downgrade() -> None:
    op.execute(DROP)
