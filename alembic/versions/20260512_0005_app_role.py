"""create app_role for production runtime

Background: PostgreSQL bypasses RLS for superusers and for roles with the
``BYPASSRLS`` attribute. The migrations in this repo are applied as
``postgres`` (a superuser), so the RLS policies created in
``0004_security_hardening`` are technically present but do not take effect
at runtime when the application also connects as ``postgres``.

This migration creates a dedicated ``app_role`` (``NOSUPERUSER NOBYPASSRLS``)
with exactly the privileges the application needs:

  * full DML on every business table,
  * ``INSERT`` only on ``audit_logs`` (mutations are blocked by trigger),
  * usage on the ``public`` schema and on sequences.

The application's ``DATABASE_URL`` should point at ``app_role`` in any
non-local environment so RLS is enforced. We do **not** change the
default URL here; see ``.env.example`` for guidance.

If the role already exists (re-running on the same DB), all statements
are no-ops thanks to ``DO $$ ... $$`` guards and ``IF NOT EXISTS``.

Revision ID: 0005_app_role
Revises: 0004_security_hardening
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_app_role"
down_revision: str | Sequence[str] | None = "0004_security_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Password is intentionally weak; operators must rotate it on first deploy
# (see ``.env.example``). It is a placeholder so the role is loginable in
# dev environments before the operator sets a real secret.
_APP_ROLE_DEFAULT_PASSWORD = "app_role_change_me"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
                CREATE ROLE app_role
                    LOGIN
                    NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOINHERIT NOREPLICATION
                    NOBYPASSRLS
                    PASSWORD '{_APP_ROLE_DEFAULT_PASSWORD}';
            END IF;
        END
        $$
        """
    )

    op.execute("GRANT CONNECT ON DATABASE coffee_loyalty TO app_role")
    op.execute("GRANT USAGE ON SCHEMA public TO app_role")

    # DML on all current and future tables in public.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
        "IN SCHEMA public TO app_role"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_role")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_role"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO app_role"
    )

    # audit_logs is append-only — strip mutation privileges.
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM app_role")


def downgrade() -> None:
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_role")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_role")
    op.execute("REVOKE ALL ON SCHEMA public FROM app_role")
    op.execute("REVOKE ALL ON DATABASE coffee_loyalty FROM app_role")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_role"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE USAGE, SELECT ON SEQUENCES FROM app_role"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
                DROP ROLE app_role;
            END IF;
        END
        $$
        """
    )
