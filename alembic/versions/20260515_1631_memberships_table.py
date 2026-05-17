"""memberships table

Revision ID: b69db76aae66
Revises: a6e77c48a422
Create Date: 2026-05-15 16:31:52.677746

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b69db76aae66'
down_revision: str | Sequence[str] | None = 'a6e77c48a422'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'memberships',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('discount_percent', sa.Integer(), nullable=False),
        sa.Column('amount_paid', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('cancelled_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('activated_by', sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','expired','cancelled')",
            name=op.f('ck_memberships_status_valid'),
        ),
        sa.CheckConstraint(
            "discount_percent BETWEEN 1 AND 100",
            name=op.f('ck_memberships_discount_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_memberships_user_id_users'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['campaign_id'], ['campaigns.id'],
            name=op.f('fk_memberships_campaign_id_campaigns'),
        ),
        sa.ForeignKeyConstraint(
            ['activated_by'], ['staff.id'],
            name=op.f('fk_memberships_activated_by_staff'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_memberships')),
    )
    op.create_index(
        'uq_membership_active', 'memberships', ['user_id'],
        unique=True, postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        'ix_membership_expiry', 'memberships', ['expires_at'],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index('ix_membership_expiry', table_name='memberships')
    op.drop_index('uq_membership_active', table_name='memberships')
    op.drop_table('memberships')
