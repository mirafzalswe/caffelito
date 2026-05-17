"""Pure-Python DTOs used by the domain layer.

Kept separate from app.schemas (which holds API/Pydantic models) so the
domain has zero web-framework coupling.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class PurchaseLine:
    """One line item in a purchase request from a staff bot."""

    product_id: uuid.UUID
    qty: int = 1
    unit_price: Decimal | None = None  # if None, taken from products.base_price
    paid_with: str = "money"  # 'money' | 'prepaid' | 'free'


@dataclass(slots=True)
class PurchaseRequest:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    user_id: uuid.UUID
    staff_id: uuid.UUID
    lines: list[PurchaseLine]
    client_request_id: str
    currency: str = "USD"
    payment_method: str | None = None
    source: str = "staff_bot"
    notes: str | None = None
    # Admin override: when set, ONLY this campaign is applied (works for
    # ``punchcard`` and ``cashback`` types), bypassing the automatic
    # stackable+priority resolution.
    force_campaign_id: uuid.UUID | None = None


@dataclass(slots=True)
class PurchaseResult:
    transaction_id: uuid.UUID
    is_replay: bool
    stamps_added_per_card: dict[uuid.UUID, int] = field(default_factory=dict)
    cards_completed: list[uuid.UUID] = field(default_factory=list)
    free_coffees_unlocked: int = 0
    cashback_earned: Decimal = Decimal("0.00")
    prepaid_consumed_per_pkg: dict[uuid.UUID, int] = field(default_factory=dict)
    # VIP membership info if the purchase used one.
    vip_charged: Decimal | None = None
    vip_balance_remaining: Decimal | None = None
