"""initial schema

Full MVP schema. Each block is executed statement-by-statement because
asyncpg requires one SQL statement per ``execute`` call.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _run(sql: str) -> None:
    """Split a multi-statement DDL block on ``;`` and execute one-by-one.

    This is safe because our DDL doesn't contain semicolons inside string
    literals or function bodies. Lines starting with ``--`` are passed
    through to the server (which ignores them).
    """
    for raw in sql.split(";"):
        stmt = raw.strip()
        if stmt:
            op.execute(stmt)


def upgrade() -> None:
    # Extensions
    _run(
        """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        CREATE EXTENSION IF NOT EXISTS citext;
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE EXTENSION IF NOT EXISTS btree_gin;
        """
    )

    # ---------- TENANTS ----------
    _run(
        """
        CREATE TABLE tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            slug CITEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL DEFAULT 'starter'
                CHECK (plan IN ('starter','growth','chain')),
            status TEXT NOT NULL DEFAULT 'trial'
                CHECK (status IN ('trial','active','suspended','churned')),
            default_currency CHAR(3) NOT NULL DEFAULT 'USD',
            default_timezone TEXT NOT NULL DEFAULT 'UTC',
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ---------- BRANCHES ----------
    _run(
        """
        CREATE TABLE branches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            address TEXT,
            timezone TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','closed','paused')),
            opening_hours JSONB,
            geo_lat DOUBLE PRECISION,
            geo_lng DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_branches_tenant_name UNIQUE (tenant_id, name)
        );
        CREATE INDEX ix_branches_tenant_active ON branches(tenant_id) WHERE status = 'active';
        """
    )

    # ---------- USERS ----------
    _run(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            phone_e164 TEXT NOT NULL,
            full_name TEXT,
            telegram_id BIGINT,
            telegram_username TEXT,
            language CHAR(2) NOT NULL DEFAULT 'ru',
            timezone TEXT,
            birthday DATE,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','blocked','merged')),
            notify_opt_in BOOLEAN NOT NULL DEFAULT TRUE,
            notify_quiet_from TIME,
            notify_quiet_to TIME,
            source TEXT,
            first_seen_at TIMESTAMPTZ,
            last_seen_at TIMESTAMPTZ,
            merged_into_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX uq_users_tenant_phone
            ON users (tenant_id, phone_e164) WHERE deleted_at IS NULL;
        CREATE UNIQUE INDEX uq_users_tenant_telegram
            ON users (tenant_id, telegram_id)
            WHERE telegram_id IS NOT NULL AND deleted_at IS NULL;
        CREATE INDEX ix_users_phone_trgm ON users USING gin (phone_e164 gin_trgm_ops);
        CREATE INDEX ix_users_active_notify ON users (tenant_id)
            WHERE deleted_at IS NULL AND notify_opt_in = TRUE AND telegram_id IS NOT NULL;
        """
    )

    # ---------- USER DASHBOARD ----------
    _run(
        """
        CREATE TABLE user_dashboard (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL,
            stamps_total INT NOT NULL DEFAULT 0,
            stamps_required INT NOT NULL DEFAULT 0,
            free_coffees_available INT NOT NULL DEFAULT 0,
            cashback_balance NUMERIC(12,2) NOT NULL DEFAULT 0,
            prepaid_remaining INT NOT NULL DEFAULT 0,
            last_visit_at TIMESTAMPTZ,
            last_visit_branch_id UUID,
            visits_30d INT NOT NULL DEFAULT 0,
            rfm_segment TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ---------- STAFF + RBAC ----------
    _run(
        """
        CREATE TABLE staff (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email CITEXT,
            phone_e164 TEXT,
            full_name TEXT NOT NULL,
            telegram_id BIGINT,
            role TEXT NOT NULL
                CHECK (role IN ('owner','manager','barista','accountant','support')),
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','suspended','left')),
            password_hash TEXT,
            pin_hash TEXT,
            totp_secret TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_staff_tenant_email UNIQUE (tenant_id, email)
        );
        CREATE UNIQUE INDEX uq_staff_tenant_telegram ON staff (tenant_id, telegram_id)
            WHERE telegram_id IS NOT NULL;
        CREATE TABLE staff_branches (
            staff_id UUID NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
            branch_id UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
            PRIMARY KEY (staff_id, branch_id)
        );
        CREATE TABLE roles (code TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE permissions (code TEXT PRIMARY KEY, description TEXT);
        CREATE TABLE role_permissions (
            role_code TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
            permission_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
            PRIMARY KEY (role_code, permission_code)
        );
        """
    )

    # Roles + permissions seed
    _run(
        """
        INSERT INTO roles (code, name) VALUES
            ('owner','Owner'),('manager','Manager'),('barista','Barista'),
            ('accountant','Accountant'),('support','Support');
        INSERT INTO permissions (code, description) VALUES
            ('purchase.create','Record a purchase'),
            ('purchase.refund','Refund a transaction'),
            ('redeem.free','Redeem a free coffee'),
            ('prepaid.open','Open a prepaid package'),
            ('prepaid.consume','Consume from a prepaid package'),
            ('bonus.grant','Manually grant a bonus'),
            ('campaign.manage','Manage campaigns'),
            ('analytics.view','View analytics dashboard'),
            ('staff.manage','Manage staff and roles'),
            ('audit.view','View audit logs'),
            ('user.merge','Merge duplicate users');
        INSERT INTO role_permissions (role_code, permission_code)
            SELECT 'owner', code FROM permissions;
        INSERT INTO role_permissions (role_code, permission_code) VALUES
            ('manager','purchase.create'),('manager','purchase.refund'),('manager','redeem.free'),
            ('manager','prepaid.open'),('manager','prepaid.consume'),('manager','bonus.grant'),
            ('manager','campaign.manage'),('manager','analytics.view'),('manager','staff.manage'),
            ('manager','audit.view'),('manager','user.merge'),
            ('barista','purchase.create'),('barista','redeem.free'),
            ('barista','prepaid.consume'),('barista','prepaid.open'),
            ('accountant','purchase.refund'),('accountant','analytics.view'),('accountant','audit.view'),
            ('support','user.merge'),('support','audit.view'),('support','bonus.grant');
        """
    )

    # ---------- PRODUCTS ----------
    _run(
        """
        CREATE TABLE products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            sku TEXT,
            name TEXT NOT NULL,
            category TEXT,
            size TEXT,
            base_price NUMERIC(12,2) NOT NULL CHECK (base_price >= 0),
            is_loyalty_eligible BOOLEAN NOT NULL DEFAULT TRUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_products_tenant_sku UNIQUE (tenant_id, sku)
        );
        CREATE INDEX ix_products_tenant_active ON products(tenant_id) WHERE is_active = TRUE;
        """
    )

    # ---------- CAMPAIGNS ----------
    _run(
        """
        CREATE TABLE campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL
                CHECK (type IN ('punchcard','prepaid','cashback','bonus_item',
                                'tiered_status','first_purchase','birthday')),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','active','paused','archived')),
            starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ends_at TIMESTAMPTZ,
            priority INT NOT NULL DEFAULT 100,
            stackable BOOLEAN NOT NULL DEFAULT FALSE,
            rules JSONB NOT NULL,
            created_by UUID REFERENCES staff(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_campaigns_tenant_code UNIQUE (tenant_id, code)
        );
        CREATE INDEX ix_campaigns_active ON campaigns(tenant_id) WHERE status = 'active';
        CREATE TABLE campaign_branches (
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            branch_id UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
            PRIMARY KEY (campaign_id, branch_id)
        );
        CREATE TABLE campaign_products (
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            PRIMARY KEY (campaign_id, product_id)
        );
        """
    )

    # ---------- LOYALTY CARDS ----------
    _run(
        """
        CREATE TABLE loyalty_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            campaign_id UUID NOT NULL REFERENCES campaigns(id),
            stamps INT NOT NULL DEFAULT 0 CHECK (stamps >= 0),
            stamps_required INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','complete','redeemed','expired')),
            opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            redeemed_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            redeemed_tx_id UUID,
            version INT NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX uq_loyalty_active ON loyalty_cards (user_id, campaign_id)
            WHERE status IN ('open','complete');
        CREATE INDEX ix_loyalty_user ON loyalty_cards(user_id);
        CREATE INDEX ix_loyalty_expiring ON loyalty_cards(expires_at)
            WHERE status IN ('open','complete');
        """
    )

    # ---------- PREPAID ----------
    _run(
        """
        CREATE TABLE prepaid_packages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            campaign_id UUID REFERENCES campaigns(id),
            product_scope JSONB NOT NULL,
            qty_total INT NOT NULL CHECK (qty_total > 0),
            qty_remaining INT NOT NULL CHECK (qty_remaining >= 0),
            amount_paid NUMERIC(12,2) NOT NULL,
            currency CHAR(3) NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','exhausted','refunded','expired','suspended')),
            opened_by UUID REFERENCES staff(id) ON DELETE SET NULL,
            opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            version INT NOT NULL DEFAULT 0,
            CONSTRAINT qty_remaining_le_total CHECK (qty_remaining <= qty_total)
        );
        CREATE INDEX ix_prepaid_user_active ON prepaid_packages(user_id) WHERE status = 'active';
        CREATE INDEX ix_prepaid_expiring ON prepaid_packages(expires_at) WHERE status = 'active';
        """
    )

    # ---------- WALLET ----------
    _run(
        """
        CREATE TABLE cashback_wallets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            currency CHAR(3) NOT NULL,
            balance NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (balance >= 0),
            version INT NOT NULL DEFAULT 0,
            CONSTRAINT uq_wallet_user_ccy UNIQUE (user_id, currency)
        );
        CREATE TABLE wallet_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wallet_id UUID NOT NULL REFERENCES cashback_wallets(id) ON DELETE CASCADE,
            amount NUMERIC(12,2) NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('earn','spend','expire','adjust','refund')),
            source_type TEXT NOT NULL,
            source_id UUID,
            expires_at TIMESTAMPTZ,
            idempotency_key TEXT NOT NULL,
            created_by UUID REFERENCES staff(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_wallet_entry_idem UNIQUE (wallet_id, idempotency_key)
        );
        CREATE INDEX ix_wallet_entries_wallet_ts ON wallet_entries(wallet_id, created_at);
        CREATE INDEX ix_wallet_entries_expiring ON wallet_entries(expires_at)
            WHERE kind = 'earn' AND expires_at IS NOT NULL;
        """
    )

    # ---------- TRANSACTIONS ----------
    _run(
        """
        CREATE TABLE transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            branch_id UUID NOT NULL REFERENCES branches(id),
            user_id UUID NOT NULL REFERENCES users(id),
            staff_id UUID NOT NULL REFERENCES staff(id),
            type TEXT NOT NULL
                CHECK (type IN ('purchase','redeem_free','prepaid_consume',
                                'manual_grant','manual_revoke','refund')),
            status TEXT NOT NULL DEFAULT 'committed'
                CHECK (status IN ('pending','committed','reversed')),
            total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
            currency CHAR(3) NOT NULL,
            payment_method TEXT,
            source TEXT NOT NULL,
            device_id TEXT,
            client_request_id TEXT NOT NULL,
            reverses UUID REFERENCES transactions(id),
            reversed_by UUID,
            notes TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tx_idempotency UNIQUE (tenant_id, client_request_id)
        );
        CREATE INDEX ix_tx_user_ts ON transactions(user_id, created_at DESC);
        CREATE INDEX ix_tx_branch_ts ON transactions(branch_id, created_at DESC);
        CREATE INDEX ix_tx_staff_ts ON transactions(staff_id, created_at DESC);
        CREATE TABLE transaction_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
            product_id UUID REFERENCES products(id),
            qty INT NOT NULL CHECK (qty > 0),
            unit_price NUMERIC(12,2) NOT NULL,
            discount NUMERIC(12,2) NOT NULL DEFAULT 0,
            paid_with TEXT NOT NULL CHECK (paid_with IN ('money','prepaid','free')),
            prepaid_package_id UUID REFERENCES prepaid_packages(id),
            loyalty_card_id UUID REFERENCES loyalty_cards(id)
        );
        CREATE INDEX ix_tx_items_tx ON transaction_items(transaction_id);
        """
    )

    # ---------- LEDGER ----------
    _run(
        """
        CREATE TABLE ledger_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL,
            transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
            account TEXT NOT NULL,
            delta NUMERIC(14,4) NOT NULL,
            unit TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_ledger_user ON ledger_entries(user_id, created_at DESC);
        CREATE INDEX ix_ledger_account ON ledger_entries(account, created_at DESC);
        CREATE INDEX ix_ledger_tx ON ledger_entries(transaction_id);
        """
    )

    # ---------- OUTBOX ----------
    _run(
        """
        CREATE TABLE outbox_events (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id UUID NOT NULL,
            type TEXT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            published_at TIMESTAMPTZ
        );
        CREATE INDEX ix_outbox_unpub ON outbox_events(id) WHERE published_at IS NULL;
        """
    )

    # ---------- AUDIT ----------
    _run(
        """
        CREATE TABLE audit_logs (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL,
            actor_type TEXT NOT NULL,
            actor_id UUID,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id UUID,
            before JSONB,
            after JSONB,
            ip INET,
            user_agent TEXT,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_audit_tenant_ts ON audit_logs(tenant_id, created_at DESC);
        CREATE INDEX ix_audit_actor ON audit_logs(actor_id, created_at DESC);
        CREATE INDEX ix_audit_target ON audit_logs(target_type, target_id);
        """
    )

    # ---------- NOTIFICATIONS ----------
    _run(
        """
        CREATE TABLE notification_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            language CHAR(2) NOT NULL,
            channel TEXT NOT NULL CHECK (channel IN ('telegram','sms','push')),
            body TEXT NOT NULL,
            buttons JSONB,
            variant TEXT NOT NULL DEFAULT 'A',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT uq_notif_tpl_unique UNIQUE (tenant_id, code, language, variant)
        );
        CREATE TABLE notification_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            template_code TEXT NOT NULL,
            scheduled_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','sent','failed','skipped','cancelled')),
            attempt INT NOT NULL DEFAULT 0,
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            sent_at TIMESTAMPTZ,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_notif_due ON notification_jobs(scheduled_at) WHERE status = 'queued';
        CREATE INDEX ix_notif_user ON notification_jobs(user_id);
        """
    )


def downgrade() -> None:
    _run(
        """
        DROP TABLE IF EXISTS notification_jobs CASCADE;
        DROP TABLE IF EXISTS notification_templates CASCADE;
        DROP TABLE IF EXISTS audit_logs CASCADE;
        DROP TABLE IF EXISTS outbox_events CASCADE;
        DROP TABLE IF EXISTS ledger_entries CASCADE;
        DROP TABLE IF EXISTS transaction_items CASCADE;
        DROP TABLE IF EXISTS transactions CASCADE;
        DROP TABLE IF EXISTS wallet_entries CASCADE;
        DROP TABLE IF EXISTS cashback_wallets CASCADE;
        DROP TABLE IF EXISTS prepaid_packages CASCADE;
        DROP TABLE IF EXISTS loyalty_cards CASCADE;
        DROP TABLE IF EXISTS campaign_products CASCADE;
        DROP TABLE IF EXISTS campaign_branches CASCADE;
        DROP TABLE IF EXISTS campaigns CASCADE;
        DROP TABLE IF EXISTS products CASCADE;
        DROP TABLE IF EXISTS role_permissions CASCADE;
        DROP TABLE IF EXISTS permissions CASCADE;
        DROP TABLE IF EXISTS roles CASCADE;
        DROP TABLE IF EXISTS staff_branches CASCADE;
        DROP TABLE IF EXISTS staff CASCADE;
        DROP TABLE IF EXISTS user_dashboard CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
        DROP TABLE IF EXISTS branches CASCADE;
        DROP TABLE IF EXISTS tenants CASCADE;
        """
    )
