"""drop manager/accountant/support roles, keep only owner and barista

Why: product decision to simplify RBAC — only owner (web admin) and
barista (in-shop POS) remain. Existing staff rows with the removed roles
are reassigned to 'owner' to preserve access for the migration window.

Revision ID: 0003_drop_extra_roles
Revises: 0002_loyalty_uq_open_only
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_drop_extra_roles"
down_revision: str | Sequence[str] | None = "0002_loyalty_uq_open_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REMOVED = ("manager", "accountant", "support")


def upgrade() -> None:
    op.execute(
        "UPDATE staff SET role = 'owner' "
        "WHERE role IN ('manager','accountant','support')"
    )
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE role_code IN ('manager','accountant','support')"
    )
    op.execute(
        "DELETE FROM roles WHERE code IN ('manager','accountant','support')"
    )

    op.execute("ALTER TABLE staff DROP CONSTRAINT IF EXISTS role_valid")
    op.execute(
        "ALTER TABLE staff ADD CONSTRAINT role_valid "
        "CHECK (role IN ('owner','barista'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE staff DROP CONSTRAINT IF EXISTS role_valid")
    op.execute(
        "ALTER TABLE staff ADD CONSTRAINT role_valid "
        "CHECK (role IN ('owner','manager','barista','accountant','support'))"
    )
    op.execute(
        """
        INSERT INTO roles (code, name) VALUES
            ('manager','Manager'),
            ('accountant','Accountant'),
            ('support','Support')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_code, permission_code) VALUES
            ('manager','purchase.create'),('manager','purchase.refund'),
            ('manager','redeem.free'),('manager','prepaid.open'),
            ('manager','prepaid.consume'),('manager','bonus.grant'),
            ('manager','campaign.manage'),('manager','analytics.view'),
            ('manager','staff.manage'),('manager','audit.view'),
            ('manager','user.merge'),
            ('accountant','purchase.refund'),('accountant','analytics.view'),
            ('accountant','audit.view'),
            ('support','user.merge'),('support','audit.view'),
            ('support','bonus.grant')
        ON CONFLICT DO NOTHING
        """
    )
