"""non-superuser application role so RLS actually applies

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


# NOTE: the dev password here must match settings.APP_DB_PASSWORD. For real
# environments, create this role out-of-band (secrets manager) rather than in a
# migration; kept inline here to keep the Phase-0 skeleton one-command runnable.
UPGRADE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cholavin_app') THEN
        CREATE ROLE cholavin_app LOGIN PASSWORD 'cholavin_app' NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO cholavin_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cholavin_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cholavin_app;

-- Future tables/sequences (Phase 1+) created by the owner auto-grant to the app role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cholavin_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO cholavin_app;
"""

DOWNGRADE = """
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM cholavin_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE USAGE, SELECT ON SEQUENCES FROM cholavin_app;
DROP OWNED BY cholavin_app;
DROP ROLE IF EXISTS cholavin_app;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
