"""Identity service — phone-first, telegram_id linked deferred.

Three flavours of lookup are supported:

* ``find_or_create_by_phone`` — used by admin/staff creating a customer.
* ``link_telegram`` — when the customer first hits /start and shares contact.
* ``find_by_telegram`` — fast path on every bot update once linked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.phone import normalize_phone
from app.domain import events
from app.domain.errors import TelegramConflict, UserBlocked, UserNotFound
from app.domain.outbox import enqueue_event
from app.models import User, UserDashboard


@dataclass
class LinkResult:
    user: User
    created: bool      # True if a new user row was inserted
    linked: bool       # True if telegram_id was set/updated this call


async def find_by_phone(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    phone: str,
) -> User | None:
    e164 = normalize_phone(phone)
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.phone_e164 == e164,
        User.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_by_telegram(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    telegram_id: int,
) -> User | None:
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.telegram_id == telegram_id,
        User.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_or_create_by_phone(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    phone: str,
    full_name: str | None = None,
    source: str = "admin",
) -> tuple[User, bool]:
    """Idempotent: same phone returns the existing row.

    Returns ``(user, created)``.
    """
    user = await find_by_phone(session, tenant_id=tenant_id, phone=phone)
    if user:
        if user.status == "blocked":
            raise UserBlocked
        return user, False

    e164 = normalize_phone(phone)
    user = User(
        tenant_id=tenant_id,
        phone_e164=e164,
        full_name=full_name,
        source=source,
        first_seen_at=now(),
    )
    session.add(user)
    await session.flush()  # populate user.id

    session.add(UserDashboard(user_id=user.id, tenant_id=tenant_id))

    await enqueue_event(
        session,
        tenant_id=tenant_id,
        aggregate_type=events.AGG_USER,
        aggregate_id=user.id,
        type_=events.EVT_USER_CREATED,
        payload={
            "user_id": str(user.id),
            "phone_e164": e164,
            "source": source,
        },
    )
    return user, True


async def link_telegram(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    phone: str,
    telegram_id: int,
    telegram_username: str | None = None,
    full_name: str | None = None,
    language: str | None = None,
) -> LinkResult:
    """Connect a Telegram account to a user identified by their verified phone.

    Behaviour:
      * phone exists, no telegram_id   → set it; ``linked=True``.
      * phone exists, telegram_id same → no-op; ``linked=False``.
      * phone exists, telegram_id diff → ``TelegramConflict`` (manual merge needed).
      * phone not found                → create new user with telegram_id; ``created=True``.
    """
    user = await find_by_phone(session, tenant_id=tenant_id, phone=phone)

    if user is None:
        e164 = normalize_phone(phone)
        user = User(
            tenant_id=tenant_id,
            phone_e164=e164,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            full_name=full_name,
            language=language or "ru",
            source="self",
            first_seen_at=now(),
            last_seen_at=now(),
        )
        session.add(user)
        await session.flush()
        session.add(UserDashboard(user_id=user.id, tenant_id=tenant_id))
        await enqueue_event(
            session,
            tenant_id=tenant_id,
            aggregate_type=events.AGG_USER,
            aggregate_id=user.id,
            type_=events.EVT_USER_LINKED,
            payload={
                "user_id": str(user.id),
                "telegram_id": telegram_id,
                "created": True,
            },
        )
        return LinkResult(user=user, created=True, linked=True)

    if user.status == "blocked":
        raise UserBlocked

    if user.telegram_id is None:
        user.telegram_id = telegram_id
        user.telegram_username = telegram_username
        if full_name and not user.full_name:
            user.full_name = full_name
        if language and not user.language:
            user.language = language
        user.last_seen_at = now()
        await session.flush()
        await enqueue_event(
            session,
            tenant_id=tenant_id,
            aggregate_type=events.AGG_USER,
            aggregate_id=user.id,
            type_=events.EVT_USER_LINKED,
            payload={
                "user_id": str(user.id),
                "telegram_id": telegram_id,
                "created": False,
            },
        )
        return LinkResult(user=user, created=False, linked=True)

    if user.telegram_id == telegram_id:
        # Already linked — touch last_seen_at and update light fields.
        user.last_seen_at = now()
        if telegram_username and user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
        return LinkResult(user=user, created=False, linked=False)

    # Phone owned by a different Telegram account → require manual resolution.
    raise TelegramConflict


async def get_or_404(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> User:
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.id == user_id,
        User.deleted_at.is_(None),
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise UserNotFound
    return user
