"""Look up a customer the barista just typed/scanned/asked about."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import InvalidPhoneError, normalize_phone
from app.domain import identity
from app.domain.redeem_code import resolve_code
from app.models import User


async def find_customer(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    raw: str,
) -> User | None:
    """Resolve a free-form input from the barista to a single customer.

    Order of attempts:
      1. 6-digit numeric → redeem code in Redis.
      2. Looks-like-phone → exact normalized E.164 match.
      3. ≥4 trailing digits → fuzzy LIKE search; return only if unique.
    """
    raw = raw.strip()

    # 1. 6-digit redeem/identify code
    if raw.isdigit() and len(raw) == 6:
        resolved = await resolve_code(tenant_id=tenant_id, code=raw)
        if resolved is not None:
            user_id, _intent = resolved
            try:
                return await identity.get_or_404(
                    session, tenant_id=tenant_id, user_id=user_id
                )
            except Exception:  # noqa: BLE001
                return None
        # falls through: maybe it's actually the last 6 digits of a phone

    # 2. phone-shaped input
    if "+" in raw or len(raw) >= 9:
        try:
            user = await identity.find_by_phone(
                session, tenant_id=tenant_id, phone=raw
            )
            if user is not None:
                return user
        except InvalidPhoneError:
            pass

    # 3. fuzzy: at least 4 trailing digits
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 4:
        like = f"%{digits}"
        stmt = (
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.phone_e164.like(like),
                User.deleted_at.is_(None),
            )
            .limit(2)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        if len(rows) == 1:
            return rows[0]

    return None
