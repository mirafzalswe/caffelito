"""Domain tests for paying (partially) with accumulated cashback.

Isolated disposable schema (see tests/test_admin_staff.py for the rationale on
``checkfirst=False``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import settings
from app.core.security import hash_secret
from app.domain import wallet as wallet_svc
from app.domain.errors import InsufficientCashback
from app.domain.loyalty_engine import record_purchase
from app.domain.refund import refund_transaction
from app.domain.schemas import PurchaseLine, PurchaseRequest
from app.models import (
    Branch,
    Campaign,
    CampaignBranch,
    CashbackWallet,
    Product,
    Staff,
    Tenant,
    User,
)
from app.models.base import Base

SCHEMA = f"test_cb_{uuid.uuid4().hex[:8]}"
CONNECT_ARGS = {"server_settings": {"search_path": f"{SCHEMA},public"}}


@pytest_asyncio.fixture
async def env() -> AsyncIterator[dict]:
    setup = create_async_engine(settings.database_url, poolclass=NullPool)
    async with setup.begin() as c:
        await c.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    await setup.dispose()

    engine = create_async_engine(
        settings.database_url, poolclass=NullPool, connect_args=CONNECT_ARGS
    )
    async with engine.begin() as c:
        await c.run_sync(lambda sc: Base.metadata.create_all(sc, checkfirst=False))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        tenant = Tenant(name="Demo", slug="demo", default_currency="UZS")
        s.add(tenant)
        await s.flush()
        branch = Branch(tenant_id=tenant.id, name="Main", timezone="Asia/Tashkent")
        staff = Staff(tenant_id=tenant.id, full_name="B", role="barista",
                      status="active", username="b", pin_hash=hash_secret("1234"))
        user = User(tenant_id=tenant.id, phone_e164="+998901234567")
        product = Product(tenant_id=tenant.id, name="Latte", base_price=Decimal("10000"))
        s.add_all([branch, staff, user, product])
        await s.flush()
        camp = Campaign(tenant_id=tenant.id, code="CB", name="Cashback 10%",
                        type="cashback", status="active", rules={"percent": 10})
        s.add(camp)
        await s.flush()
        s.add(CampaignBranch(campaign_id=camp.id, branch_id=branch.id))
        # Top up the customer's wallet with 5000 cashback.
        await wallet_svc.credit(
            s, tenant_id=tenant.id, user_id=user.id, currency="UZS",
            amount=Decimal("5000"), source_type="manual", source_id=None,
            idempotency_key="seed-topup",
        )
        await s.commit()
        ids = {
            "tenant": tenant.id, "branch": branch.id, "staff": staff.id,
            "user": user.id, "product": product.id,
        }

    yield {"Session": Session, **ids}

    await engine.dispose()
    drop = create_async_engine(settings.database_url, poolclass=NullPool)
    async with drop.begin() as c:
        await c.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
    await drop.dispose()


def _req(env, *, cashback: Decimal, crid: str) -> PurchaseRequest:
    return PurchaseRequest(
        tenant_id=env["tenant"], branch_id=env["branch"], user_id=env["user"],
        staff_id=env["staff"],
        lines=[PurchaseLine(product_id=env["product"], qty=1, paid_with="money")],
        client_request_id=crid, currency="UZS", source="staff_bot",
        cashback_to_spend=cashback,
    )


async def _balance(Session, user_id) -> Decimal:
    async with Session() as s:
        return Decimal(
            (await s.execute(
                select(CashbackWallet.balance).where(CashbackWallet.user_id == user_id)
            )).scalar_one()
        )


@pytest.mark.asyncio
async def test_partial_cashback_payment(env):
    Session = env["Session"]
    async with Session() as s:
        res = await record_purchase(s, request=_req(env, cashback=Decimal("4000"), crid="p1"))
        await s.commit()

    # 4000 cashback applied, 6000 cash due, cashback earned on the 6000 cash @10% = 600.
    assert res.cashback_spent == Decimal("4000.00")
    assert res.cash_due == Decimal("6000.00")
    assert res.cashback_earned == Decimal("600.00")
    # Wallet: 5000 - 4000 spent + 600 earned = 1600.
    assert await _balance(Session, env["user"]) == Decimal("1600.00")


@pytest.mark.asyncio
async def test_cashback_capped_at_bill(env):
    Session = env["Session"]
    async with Session() as s:
        # Ask to spend more than the 10000 bill — capped to 10000, but balance
        # is only 5000 → InsufficientCashback, whole purchase rolls back.
        with pytest.raises(InsufficientCashback):
            await record_purchase(s, request=_req(env, cashback=Decimal("99999"), crid="p2"))
        await s.rollback()
    # Nothing spent.
    assert await _balance(Session, env["user"]) == Decimal("5000.00")


@pytest.mark.asyncio
async def test_refund_restores_spent_cashback(env):
    Session = env["Session"]
    async with Session() as s:
        res = await record_purchase(s, request=_req(env, cashback=Decimal("3000"), crid="p3"))
        await s.commit()
    # 5000 - 3000 + (7000*10% = 700) = 2700
    assert await _balance(Session, env["user"]) == Decimal("2700.00")

    async with Session() as s:
        await refund_transaction(
            s, tenant_id=env["tenant"], branch_id=env["branch"], staff_id=env["staff"],
            transaction_id=res.transaction_id, reason="test", client_request_id="r3",
        )
        await s.commit()
    # Refund restores the 3000 spent and claws back the 700 earned → back to 5000.
    assert await _balance(Session, env["user"]) == Decimal("5000.00")
