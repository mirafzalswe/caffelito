"""Short-lived numeric codes the customer shows the barista to redeem free/prepaid.

Stored in Redis with a 5-minute TTL. The barista's bot resolves code → user_id
on consumption. Codes are scoped to ``redeem:{code}`` so two users can't share
the same code at the same moment (collision is extremely unlikely with 6 digits
across at most a few thousand active users, but we still guard).
"""

from __future__ import annotations

import uuid

from app.core.redis import get_redis
from app.core.security import random_redeem_code

REDEEM_TTL = 300  # 5 minutes
NS = "redeem"


async def issue_code(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    intent: str,  # 'free' | 'prepaid'
) -> str:
    """Generate a code, store the binding, return the code."""
    redis = get_redis()
    for _ in range(5):
        code = random_redeem_code(6)
        key = f"{NS}:{tenant_id}:{code}"
        ok = await redis.set(
            key,
            f"{user_id}|{intent}",
            ex=REDEEM_TTL,
            nx=True,
        )
        if ok:
            return code
    raise RuntimeError("Could not allocate a redeem code; try again")


async def resolve_code(
    *,
    tenant_id: uuid.UUID,
    code: str,
) -> tuple[uuid.UUID, str] | None:
    """Return (user_id, intent) if the code is valid, else None.

    The code is consumed (deleted) on resolution to prevent re-use.
    """
    redis = get_redis()
    key = f"{NS}:{tenant_id}:{code}"
    val = await redis.get(key)
    if val is None:
        return None
    await redis.delete(key)
    user_str, intent = val.split("|", 1)
    return uuid.UUID(user_str), intent
