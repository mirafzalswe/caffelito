"""security hardening: RLS policies + audit immutability + notification dedup

What this migration does:

1. RLS — enables ``ROW LEVEL SECURITY`` (with ``FORCE`` so it applies to the
   table owner too) on every tenant-scoped table that has a direct
   ``tenant_id`` column. A single permissive policy is created per table:

       USING (
           current_setting('app.tenant_id', true) IS NULL
        OR current_setting('app.tenant_id', true) = ''
        OR tenant_id::text = current_setting('app.tenant_id', true)
       )

   The empty/NULL fallback keeps cross-tenant system jobs and migrations
   working (``session_scope`` called without ``tenant_id``). When the
   application sets ``app.tenant_id`` via ``set_config``, the policy
   enforces tenant isolation.

2. ``audit_logs`` immutability — installs a ``BEFORE UPDATE OR DELETE``
   trigger that raises an exception. This makes the table append-only at
   the database level, satisfying §3.13 of the implementation plan.

3. ``notification_jobs`` dedup — adds a ``dedup_key`` column and a partial
   unique index so the publisher cannot enqueue duplicate jobs for the
   same (user, template, payload-hash) within the window the producer
   chooses. NULL keys disable dedup for legacy callers.

Revision ID: 0004_security_hardening
Revises: 0003_drop_extra_roles
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_security_hardening"
down_revision: str | Sequence[str] | None = "0003_drop_extra_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables that carry a ``tenant_id`` column and warrant RLS isolation.
_RLS_TABLES_TENANT_SCOPED = (
    "branches",
    "users",
    "staff",
    "products",
    "campaigns",
    "loyalty_cards",
    "prepaid_packages",
    "cashback_wallets",
    "transactions",
    "ledger_entries",
    "outbox_events",
    "audit_logs",
    "notification_jobs",
    "notification_templates",
    "user_dashboard",
)


def _enable_rls_for_tenant_column(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table}")
    op.execute(
        f"""
        CREATE POLICY rls_tenant_isolation ON {table}
        USING (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        """
    )


def upgrade() -> None:
    # ---- 1. RLS on tenant-scoped tables -------------------------------------
    for tbl in _RLS_TABLES_TENANT_SCOPED:
        _enable_rls_for_tenant_column(tbl)

    # tenants itself uses ``id`` as the comparison column.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS rls_tenant_isolation ON tenants")
    op.execute(
        """
        CREATE POLICY rls_tenant_isolation ON tenants
        USING (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR id::text = current_setting('app.tenant_id', true)
        )
        """
    )

    # ---- 2. audit_logs immutability -----------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_block_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs is append-only; % is not permitted', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs")
    op.execute(
        "CREATE TRIGGER audit_logs_no_update "
        "BEFORE UPDATE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()"
    )
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs")
    op.execute(
        "CREATE TRIGGER audit_logs_no_delete "
        "BEFORE DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()"
    )

    # ---- 3. notification_jobs dedup -----------------------------------------
    op.execute("ALTER TABLE notification_jobs ADD COLUMN IF NOT EXISTS dedup_key TEXT")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_dedup
            ON notification_jobs (user_id, template_code, dedup_key)
            WHERE dedup_key IS NOT NULL AND status <> 'cancelled'
        """
    )


def downgrade() -> None:
    # ---- 3. drop dedup ------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS uq_notif_dedup")
    op.execute("ALTER TABLE notification_jobs DROP COLUMN IF EXISTS dedup_key")

    # ---- 2. drop audit triggers ---------------------------------------------
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_block_mutation()")

    # ---- 1. drop RLS --------------------------------------------------------
    for tbl in (*_RLS_TABLES_TENANT_SCOPED, "tenants"):
        op.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
