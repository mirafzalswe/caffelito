"""broadcasts table

Revision ID: a6e77c48a422
Revises: 0006_wallet_fifo_tracking
Create Date: 2026-05-15 14:57:51.629017

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a6e77c48a422'
down_revision: str | Sequence[str] | None = '0006_wallet_fifo_tracking'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'broadcasts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('media_path', sa.String(length=500), nullable=True),
        sa.Column('media_type', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
        sa.Column('total_recipients', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('sent_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('failed_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('sent_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "media_type IS NULL OR media_type IN ('photo','video')",
            name=op.f('ck_broadcasts_media_type_valid'),
        ),
        sa.CheckConstraint(
            "status IN ('draft','sending','done','failed')",
            name=op.f('ck_broadcasts_status_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['staff.id'],
            name=op.f('fk_broadcasts_created_by_staff'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'],
            name=op.f('fk_broadcasts_tenant_id_tenants'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_broadcasts')),
    )
    op.create_index(
        'ix_broadcasts_tenant', 'broadcasts',
        ['tenant_id', 'created_at'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_broadcasts_tenant', table_name='broadcasts')
    op.drop_table('broadcasts')
