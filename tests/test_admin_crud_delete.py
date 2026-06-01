"""Integration tests for admin delete/archive CRUD endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.admin.auth import COOKIE_NAME, encode_session
from app.core.config import settings
from app.core.security import hash_secret
from app.models import Branch, Campaign, Product, Staff, Tenant, User
from app.models.base import Base

SCHEMA = f"test_del_{uuid.uuid4().hex[:8]}"
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
        product = Product(tenant_id=tenant.id, name="Latte", base_price=Decimal("10000"))
        camp = Campaign(tenant_id=tenant.id, code="CB", name="CB", type="cashback",
                        status="active", rules={"percent": 5})
        s.add_all([owner, branch, user, product, camp])
        await s.commit()
        ids = {"tenant": tenant.id, "owner": owner.id, "user": user.id,
               "product": product.id, "camp": camp.id}
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


async def _count(env, model, **where) -> int:
    async with env["Session"]() as s:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return (await s.execute(q)).scalar()


@pytest.mark.asyncio
async def test_delete_unused_product_and_campaign(env, client):
    assert client.post(f"/admin/products/{env['product']}/delete",
                       follow_redirects=False).status_code == 303
    assert await _count(env, Product, id=env["product"]) == 0

    assert client.post(f"/admin/campaigns/{env['camp']}/delete",
                       follow_redirects=False).status_code == 303
    assert await _count(env, Campaign, id=env["camp"]) == 0


@pytest.mark.asyncio
async def test_soft_delete_customer(env, client):
    assert client.post(f"/admin/customers/{env['user']}/delete",
                       follow_redirects=False).status_code == 303
    async with env["Session"]() as s:
        deleted_at = (await s.execute(
            select(User.deleted_at).where(User.id == env["user"])
        )).scalar_one()
    assert deleted_at is not None
    # The customer list no longer shows them.
    body = client.get("/admin/customers/").text
    assert "+998901234567" not in body


@pytest.mark.asyncio
async def test_cannot_delete_self(env, client):
    r = client.post(f"/admin/staff/{env['owner']}/delete", follow_redirects=False)
    assert r.status_code == 303 and "err=self" in r.headers["location"]
    assert await _count(env, Staff, id=env["owner"]) == 1
