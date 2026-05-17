"""Map a Telegram bot token to its owning tenant.

For MVP we use a simple heuristic:
* if there is exactly one tenant in the DB, every bot belongs to it;
* otherwise the env-var ``BOT_TENANT_ID`` overrides;
* later (V2) tenants will own per-bot tokens via a ``tenant_bots`` table.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant


async def resolve_tenant(session: AsyncSession) -> uuid.UUID:
    forced = os.getenv("BOT_TENANT_ID")
    if forced:
        return uuid.UUID(forced)

    rows = (await session.execute(select(Tenant.id).limit(2))).scalars().all()
    if len(rows) == 0:
        raise RuntimeError(
            "No tenant exists yet. Run scripts/seed.py to create a demo tenant."
        )
    if len(rows) > 1:
        raise RuntimeError(
            "Multiple tenants present; set BOT_TENANT_ID env var to disambiguate."
        )
    return rows[0]

