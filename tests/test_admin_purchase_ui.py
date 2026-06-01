"""Integration test: admin customer-detail purchase UI (categorized picker +
cashback payment). Isolated disposable schema."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.admin.auth import COOKIE_NAME, encode_session
from app.core.config import settings
from app.core.security import hash_secret
from app.domain import wallet as wallet_svc
from app.domain.loyalty_engine import _refresh_user_dashboard_projection
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

SCHEMA = f"test_pui_{uuid.uuid4().hex[:8]}"
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
        owner = Staff(tenant_id=tenant.id, full_name="O", role="owner", status="active",
                      username="boss", password_hash=hash_secret("secret123"))
        branch = Branch(tenant_id=tenant.id, name="Main", timezone="Asia/Tashkent")
        user = User(tenant_id=tenant.id, phone_e164="+998901234567")
        s.add_all([owner, branch, user])
        await s.flush()
        # A hot coffee + an iced coffee + a sweet, to exercise grouping.
        s.add_all([
            Product(tenant_id=tenant.id, name="Капучино", category="coffee", size="M",
                    base_price=Decimal("24000")),
            Product(tenant_id=tenant.id, name="Айс Латте", category="coffee", size="L",
                    base_price=Decimal("28000")),
            Product(tenant_id=tenant.id, name="Cookies", category="food",
                    base_price=Decimal("12000"), is_loyalty_eligible=False),
        ])
        camp = Campaign(tenant_id=tenant.id, code="CB", name="CB10", type="cashback",
                        status="active", rules={"percent": 10})
        s.add(camp)
        await s.flush()
        s.add(CampaignBranch(campaign_id=camp.id, branch_id=branch.id))
        await wallet_svc.credit(s, tenant_id=tenant.id, user_id=user.id, currency="UZS",
                                amount=Decimal("10000"), source_type="manual",
                                source_id=None, idempotency_key="seed")
        await _refresh_user_dashboard_projection(s, user_id=user.id)
        await s.commit()
        ids = {"tenant": tenant.id, "owner": owner.id, "branch": branch.id,
               "user": user.id}
        capp = (await s.execute(select(Product).where(Product.name == "Капучино"))).scalar_one()
        ids["capp"] = capp.id

    yield {"Session": Session, **ids}

    await engine.dispose()
    drop = create_async_engine(settings.database_url, poolclass=NullPool)
    async with drop.begin() as c:
        await c.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
    await drop.dispose()


@pytest.fixture
def client(env) -> Iterator:
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.main import app

    async def _override() -> AsyncIterator:
        async with env["Session"]() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, encode_session(staff_id=env["owner"], tenant_id=env["tenant"]))
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_detail_renders_categorized_picker_and_cashback(env, client):
    r = client.get(f"/admin/customers/{env['user']}")
    assert r.status_code == 200
    html = r.text
    # Categorized picker present with all three groups.
    assert "prod-tile" in html and "prod-tabs" in html
    assert "Горячий кофе" in html and "Холодное" in html and "Сладкое" in html
    # Cashback payment block shown (balance > 0).
    assert 'name="cashback_to_spend"' in html


@pytest.mark.asyncio
async def test_purchase_with_cashback_via_admin(env, client):
    r = client.post(
        f"/admin/customers/{env['user']}/purchase",
        data={
            "branch_id": str(env["branch"]),
            "product_id": str(env["capp"]),  # 24000
            "qty": "1",
            "campaign_id": "",
            "cashback_to_spend": "5000",
            "client_request_id": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    async with env["Session"]() as s:
        bal = Decimal(
            (await s.execute(
                select(CashbackWallet.balance).where(CashbackWallet.user_id == env["user"])
            )).scalar_one()
        )
    # 10000 - 5000 spent + (19000 * 10% = 1900) earned = 6900.
    assert bal == Decimal("6900.00")
