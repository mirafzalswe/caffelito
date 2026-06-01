"""Integration tests for admin EDIT (update) forms: product, branch, staff."""

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
from app.core.security import hash_secret, verify_secret
from app.models import Branch, Product, Staff, Tenant
from app.models.base import Base

SCHEMA = f"test_edit_{uuid.uuid4().hex[:8]}"
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
        branch = Branch(tenant_id=tenant.id, name="Old", timezone="Asia/Tashkent")
        product = Product(tenant_id=tenant.id, name="Latte", category="coffee",
                          size="M", base_price=Decimal("10000"))
        barista = Staff(tenant_id=tenant.id, full_name="Bar", role="barista",
                        status="active", username="bar1", phone_e164="+998901234567",
                        password_hash=hash_secret("barpass1"), pin_hash=hash_secret("1234"))
        s.add_all([owner, branch, product, barista])
        await s.commit()
        ids = {"tenant": tenant.id, "owner": owner.id, "branch": branch.id,
               "product": product.id, "barista": barista.id}
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


def test_product_edit_renders_and_updates(env, client):
    # Edit mode renders prefilled.
    page = client.get(f"/admin/products/?edit={env['product']}")
    assert page.status_code == 200 and "Latte" in page.text and "Редактировать" in page.text

    r = client.post(f"/admin/products/{env['product']}/edit", data={
        "name": "Flat White", "base_price": "26000", "sku": "FW-M",
        "category": "coffee", "size": "L", "is_loyalty_eligible": "on",
    }, follow_redirects=False)
    assert r.status_code == 303

    import asyncio

    async def check():
        async with env["Session"]() as s:
            p = (await s.execute(select(Product).where(Product.id == env["product"]))).scalar_one()
            return p.name, str(p.base_price), p.size
    name, price, size = asyncio.get_event_loop().run_until_complete(check())
    assert name == "Flat White" and price.startswith("26000") and size == "L"


def test_branch_edit_updates(env, client):
    r = client.post(f"/admin/branches/{env['branch']}/edit", data={
        "name": "New Name", "address": "Center 1", "timezone": "Asia/Tashkent",
    }, follow_redirects=False)
    assert r.status_code == 303
    import asyncio

    async def check():
        async with env["Session"]() as s:
            b = (await s.execute(select(Branch).where(Branch.id == env["branch"]))).scalar_one()
            return b.name, b.address
    name, address = asyncio.get_event_loop().run_until_complete(check())
    assert name == "New Name" and address == "Center 1"


def test_staff_edit_blank_password_keeps_hash(env, client):
    import asyncio

    async def hash_before():
        async with env["Session"]() as s:
            return (await s.execute(select(Staff.password_hash).where(Staff.id == env["barista"]))).scalar_one()
    before = asyncio.get_event_loop().run_until_complete(hash_before())

    # Rename + change username, leave password & pin blank → unchanged.
    r = client.post(f"/admin/staff/{env['barista']}/edit", data={
        "full_name": "Bar Renamed", "role": "barista", "phone": "+998901234567",
        "username": "bar1", "password": "", "pin": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    async def after():
        async with env["Session"]() as s:
            row = (await s.execute(select(Staff).where(Staff.id == env["barista"]))).scalar_one()
            return row.full_name, row.password_hash, row.pin_hash
    name, pw, pin = asyncio.get_event_loop().run_until_complete(after())
    assert name == "Bar Renamed"
    assert pw == before  # blank password left the hash untouched
    assert pin is not None and verify_secret(pin, "1234")  # PIN unchanged
