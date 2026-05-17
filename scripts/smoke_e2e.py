"""End-to-end smoke test against the live demo DB.

Verifies the core MVP loop on a *fresh* user so the script is safe to
re-run repeatedly without pre-cleanup:

    1. find_or_create_by_phone (random phone) → user created
    2. record_purchase × 10 → card auto-completes
    3. replay one purchase → ``is_replay=True``
    4. redeem_free_coffee → card transitions to ``redeemed``
    5. open prepaid 5-pack → consume one → 4 remaining
    6. refund_transaction (one of the purchases) → stamp goes back
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core.db import session_scope
from app.domain import identity, prepaid as prepaid_svc, redeem
from app.domain import refund as refund_svc
from app.domain.dashboard import read_dashboard
from app.domain.loyalty_engine import record_purchase
from app.domain.schemas import PurchaseLine, PurchaseRequest
from app.models import Branch, Product, Staff, Tenant


def _fresh_phone() -> str:
    # +998 90 XXXXXXX is a valid Beeline UZ mobile range; the trailing 7
    # digits give us 10^7 distinct numbers — comfortably unique per run.
    digits = int.from_bytes(uuid.uuid4().bytes[:4], "big") % 10_000_000
    return f"+99890{digits:07d}"


async def main() -> None:
    run = uuid.uuid4().hex[:8]
    phone = _fresh_phone()

    async with session_scope() as session:
        tenant = (await session.execute(select(Tenant).limit(1))).scalar_one()
        branch = (
            await session.execute(select(Branch).where(Branch.tenant_id == tenant.id))
        ).scalar_one()
        staff = (
            await session.execute(
                select(Staff).where(
                    Staff.tenant_id == tenant.id, Staff.role == "barista"
                )
            )
        ).scalar_one()
        cappuccino = (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == tenant.id, Product.sku == "CAPP-M"
                )
            )
        ).scalar_one()

        user, created = await identity.find_or_create_by_phone(
            session,
            tenant_id=tenant.id,
            phone=phone,
            full_name=f"Smoke User {run}",
            source="smoke",
        )
        print(f"User: {user.id} (created={created}, phone={phone})")

    purchase_tx_ids: list[uuid.UUID] = []
    for i in range(10):
        async with session_scope() as session:
            req = PurchaseRequest(
                tenant_id=tenant.id,
                branch_id=branch.id,
                user_id=user.id,
                staff_id=staff.id,
                lines=[PurchaseLine(product_id=cappuccino.id, qty=1)],
                client_request_id=f"{run}-buy-{i}",
                currency="USD",
            )
            result = await record_purchase(session, request=req)
        purchase_tx_ids.append(result.transaction_id)
        print(
            f"  buy #{i+1}  unlocked={result.free_coffees_unlocked} "
            f"completed={len(result.cards_completed)}"
        )

    async with session_scope() as session:
        view = await read_dashboard(session, user_id=user.id)
        print(
            f"\nAfter 10 buys: stamps={view.stamps_total}/{view.stamps_required} "
            f"free={view.free_coffees_available} prepaid={view.prepaid_remaining}"
        )

    # Idempotency
    async with session_scope() as session:
        req = PurchaseRequest(
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            staff_id=staff.id,
            lines=[PurchaseLine(product_id=cappuccino.id, qty=1)],
            client_request_id=f"{run}-buy-3",
            currency="USD",
        )
        replay = await record_purchase(session, request=req)
    print(f"Replay tx={replay.transaction_id} is_replay={replay.is_replay}")

    # Redeem free coffee
    async with session_scope() as session:
        tx_id = await redeem.redeem_free_coffee(
            session,
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            staff_id=staff.id,
            product_id=cappuccino.id,
            client_request_id=f"{run}-redeem-1",
        )
    print(f"Redeemed free coffee: tx={tx_id}")

    # Open + consume prepaid
    async with session_scope() as session:
        tx_open, pkg_id = await prepaid_svc.open_package(
            session,
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            staff_id=staff.id,
            qty=5,
            amount_paid=Decimal("10.00"),
            currency="USD",
            product_scope={"all": True},
            client_request_id=f"{run}-open-1",
        )
    print(f"Opened prepaid: pkg={pkg_id}")

    async with session_scope() as session:
        tx_use, _ = await prepaid_svc.consume_one(
            session,
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            staff_id=staff.id,
            product_id=cappuccino.id,
            client_request_id=f"{run}-use-1",
        )
        view = await read_dashboard(session, user_id=user.id)
    print(
        f"After prepaid use: stamps={view.stamps_total}/{view.stamps_required} "
        f"free={view.free_coffees_available} prepaid={view.prepaid_remaining}"
    )

    # Refund one of the early purchases — stamps should go back.
    refund_target = purchase_tx_ids[0]
    async with session_scope() as session:
        refund_tx = await refund_svc.refund_transaction(
            session,
            tenant_id=tenant.id,
            branch_id=branch.id,
            staff_id=staff.id,
            transaction_id=refund_target,
            reason="smoke",
            client_request_id=f"{run}-refund-1",
        )
        view = await read_dashboard(session, user_id=user.id)
    print(
        f"Refunded {refund_target} → {refund_tx}; "
        f"stamps={view.stamps_total}/{view.stamps_required} "
        f"free={view.free_coffees_available} prepaid={view.prepaid_remaining}"
    )


if __name__ == "__main__":
    asyncio.run(main())
