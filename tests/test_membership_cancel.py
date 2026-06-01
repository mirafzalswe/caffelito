"""Cancel a customer's active VIP membership — domain + admin route."""

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
from app.domain import membership as membership_svc
from app.models import Branch, Campaign, Membership, Staff, Tenant, User
from app.models.base import Base

SCHEMA = f"test_vc_{uuid.uuid4().hex[:8]}"
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
        tenant = Tenant(name="D", slug="demo", default_currency="UZS")
        s.add(tenant)
        await s.flush()
        owner = Staff(tenant_id=tenant.id, full_name="O", role="owner", status="active",
                      username="boss", password_hash=hash_secret("secret123"))
        branch = Branch(tenant_id=tenant.id, name="M", timezone="Asia/Tashkent")
        user = User(tenant_id=tenant.id, phone_e164="+998901234567")
        s.add_all([owner, branch, user])
        await s.flush()
        camp = Campaign(tenant_id=tenant.id, code="VIP", name="VIP", type="tiered_status",
                        status="active", rules={"discount_percent": 10, "entry_amount": 0})
        s.add(camp)
        await s.flush()
        m = Membership(tenant_id=tenant.id, user_id=user.id, campaign_id=camp.id,
                       discount_percent=10, amount_paid=Decimal("100000"),
                       balance_remaining=Decimal("100000"), status="active")
        s.add(m)
        await s.commit()
        ids = {"tenant": tenant.id, "owner": owner.id, "user": user.id}
    yield {"Session": Session, **ids}
    await engine.dispose()
    drop = create_async_engine(settings.database_url, poolclass=NullPool)
    async with drop.begin() as c:
        await c.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
    await drop.dispose()


@pytest.mark.asyncio
async def test_cancel_membership_domain(env):
    Session = env["Session"]
    async with Session() as s:
        m = await membership_svc.cancel_membership(
            s, tenant_id=env["tenant"], user_id=env["user"]
        )
        await s.commit()
    assert m is not None

    async with Session() as s:
        row = (await s.execute(select(Membership.status, Membership.cancelled_at))).one()
    assert row.status == "cancelled" and row.cancelled_at is not None

    # Idempotent-ish: second cancel finds nothing active.
    async with Session() as s:
        again = await membership_svc.cancel_membership(
            s, tenant_id=env["tenant"], user_id=env["user"]
        )
    assert again is None


@pytest.mark.asyncio
async def test_cancel_membership_via_admin(env):
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.main import app

    async def _override() -> AsyncIterator:
        async with env["Session"]() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        c = TestClient(app)
        c.cookies.set(COOKIE_NAME, encode_session(staff_id=env["owner"], tenant_id=env["tenant"]))
        r = c.post(f"/admin/customers/{env['user']}/membership/cancel", follow_redirects=False)
        assert r.status_code == 303
    finally:
        app.dependency_overrides.pop(get_session, None)

    async with env["Session"]() as s:
        status_ = (await s.execute(select(Membership.status))).scalar_one()
    assert status_ == "cancelled"
