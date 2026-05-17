"""Debug single purchase to expose state."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import session_scope
from app.domain import identity
from app.domain.loyalty_engine import _load_active_campaigns, record_purchase
from app.domain.schemas import PurchaseLine, PurchaseRequest
from app.models import Branch, LoyaltyCard, Product, Staff, Tenant


async def main() -> None:
    async with session_scope() as session:
        tenant = (await session.execute(select(Tenant).limit(1))).scalar_one()
        branch = (
            await session.execute(select(Branch).where(Branch.tenant_id == tenant.id))
        ).scalar_one()
        staff = (
            await session.execute(select(Staff).where(Staff.tenant_id == tenant.id))
        ).scalar_one()
        capp = (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == tenant.id, Product.sku == "CAPP-M"
                )
            )
        ).scalar_one()
        user, _ = await identity.find_or_create_by_phone(
            session, tenant_id=tenant.id, phone="+998901234599", source="dbg"
        )

    for i in range(11):
        async with session_scope() as session:
            cards = (
                await session.execute(
                    select(LoyaltyCard).where(LoyaltyCard.user_id == user.id)
                )
            ).scalars().all()
            campaigns = await _load_active_campaigns(
                session,
                tenant_id=tenant.id,
                branch_id=branch.id,
                product_ids=[capp.id],
            )
            print(
                f"\n=== before buy #{i+1}: cards="
                + ", ".join(f"{c.stamps}/{c.stamps_required}({c.status})" for c in cards)
                + f"  campaigns={len(campaigns)}"
            )
            req = PurchaseRequest(
                tenant_id=tenant.id,
                branch_id=branch.id,
                user_id=user.id,
                staff_id=staff.id,
                lines=[PurchaseLine(product_id=capp.id, qty=1)],
                client_request_id=f"dbg-{i}",
                currency="USD",
            )
            try:
                result = await record_purchase(session, request=req)
                print(
                    f"  → unlocked={result.free_coffees_unlocked} "
                    f"completed={result.cards_completed} "
                    f"stamps_added={result.stamps_added_per_card}"
                )
            except Exception as exc:
                print(f"  → ERROR: {type(exc).__name__}: {exc}")
                break


if __name__ == "__main__":
    asyncio.run(main())
