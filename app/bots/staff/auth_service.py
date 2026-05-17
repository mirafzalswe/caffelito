"""Staff authentication: PIN lookup + assigned-branch resolution."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_secret
from app.models import Branch, Staff, StaffBranch


async def find_staff_by_telegram(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    telegram_id: int,
) -> Staff | None:
    stmt = select(Staff).where(
        Staff.tenant_id == tenant_id,
        Staff.telegram_id == telegram_id,
        Staff.status == "active",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_staff_by_pin(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    pin: str,
) -> Staff | None:
    """Return the active staff whose PIN matches.

    Note: linear scan over staff with a non-null pin_hash. Acceptable for the
    expected size (tens of employees per tenant). If we ever need to scale,
    we'll prefix codes by `staff_id` in the staff bot deep-link.
    """
    stmt = select(Staff).where(
        Staff.tenant_id == tenant_id,
        Staff.status == "active",
        Staff.pin_hash.is_not(None),
    )
    candidates = (await session.execute(stmt)).scalars().all()
    for s in candidates:
        if s.pin_hash and verify_secret(s.pin_hash, pin):
            return s
    return None


async def list_staff_branches(
    session: AsyncSession,
    *,
    staff_id: uuid.UUID,
) -> list[Branch]:
    stmt = (
        select(Branch)
        .join(StaffBranch, StaffBranch.branch_id == Branch.id)
        .where(StaffBranch.staff_id == staff_id, Branch.status == "active")
        .order_by(Branch.name)
    )
    return list((await session.execute(stmt)).scalars().all())
