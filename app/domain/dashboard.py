"""Read-side helpers for the customer bot home screen and history."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, UserDashboard


@dataclass(slots=True)
class DashboardView:
    stamps_total: int
    stamps_required: int
    free_coffees_available: int
    cashback_balance: Decimal
    prepaid_remaining: int
    last_visit_at: datetime | None


async def read_dashboard(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> DashboardView:
    stmt = select(UserDashboard).where(UserDashboard.user_id == user_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return DashboardView(
            stamps_total=0,
            stamps_required=0,
            free_coffees_available=0,
            cashback_balance=Decimal("0.00"),
            prepaid_remaining=0,
            last_visit_at=None,
        )
    return DashboardView(
        stamps_total=row.stamps_total,
        stamps_required=row.stamps_required,
        free_coffees_available=row.free_coffees_available,
        cashback_balance=Decimal(str(row.cashback_balance)),
        prepaid_remaining=row.prepaid_remaining,
        last_visit_at=row.last_visit_at,
    )


async def recent_transactions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 20,
) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
