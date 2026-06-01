"""Integration tests for owner-driven staff creation + username login.

Runs against the Postgres in DATABASE_URL but inside a disposable schema.
We create the full model set with ``checkfirst=False`` so every table lives
in the test schema (first in ``search_path``) and writes never touch ``public``
— the shared dev tables are referenced only for the ``citext`` type, resolved
via ``public`` later in the path.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (register all models on Base.metadata)
from app.admin.auth import COOKIE_NAME, encode_session
from app.core.config import settings
from app.core.security import hash_secret
from app.models import Staff, Tenant
from app.models.base import Base

SCHEMA = f"test_staff_{uuid.uuid4().hex[:8]}"
CONNECT_ARGS = {"server_settings": {"search_path": f"{SCHEMA},public"}}


@pytest_asyncio.fixture
async def ctx() -> AsyncIterator[dict]:
    create = create_async_engine(settings.database_url, poolclass=NullPool)
    async with create.begin() as c:
        await c.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    await create.dispose()

    engine = create_async_engine(
        settings.database_url, poolclass=NullPool, connect_args=CONNECT_ARGS
    )
    async with engine.begin() as c:
        await c.run_sync(lambda sc: Base.metadata.create_all(sc, checkfirst=False))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        tenant = Tenant(name="Demo", slug="demo")
        s.add(tenant)
        await s.flush()
        owner = Staff(
            tenant_id=tenant.id,
            full_name="Owner",
            role="owner",
            status="active",
            username="boss",
            phone_e164="+998900000000",
            password_hash=hash_secret("secret123"),
        )
        s.add(owner)
        await s.commit()
        tenant_id, owner_id = tenant.id, owner.id

    yield {"engine": engine, "Session": Session, "tenant_id": tenant_id, "owner_id": owner_id}

    await engine.dispose()
    drop = create_async_engine(settings.database_url, poolclass=NullPool)
    async with drop.begin() as c:
        await c.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
    await drop.dispose()


@pytest.fixture
def client(ctx) -> Iterator:
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.main import app

    async def _override() -> AsyncIterator:
        async with ctx["Session"]() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    c = TestClient(app)
    c.cookies.set(
        COOKIE_NAME,
        encode_session(staff_id=ctx["owner_id"], tenant_id=ctx["tenant_id"]),
    )
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


def _new(client, **data):
    return client.post("/admin/staff/new", data=data, follow_redirects=False)


@pytest.mark.asyncio
async def test_create_barista_and_owner(ctx, client):
    assert client.get("/admin/staff/").status_code == 200

    # Barista: phone + username + password + PIN
    r = _new(client, full_name="Bar", role="barista", phone="+998901234567",
             username="bar1", password="pass1234", pin="4321")
    assert r.status_code == 303

    # Owner: phone normalised from a local-format number, no PIN
    r = _new(client, full_name="Own", role="owner", phone="998935551122",
             username="own2", password="pass5678")
    assert r.status_code == 303

    async with ctx["Session"]() as s:
        rows = {
            row.username: row
            for row in (
                await s.execute(
                    select(Staff.username, Staff.role, Staff.phone_e164, Staff.pin_hash)
                )
            ).all()
        }
    assert rows["bar1"].pin_hash is not None and rows["bar1"].role == "barista"
    assert rows["own2"].pin_hash is None and rows["own2"].phone_e164 == "+998935551122"


@pytest.mark.asyncio
async def test_validation_rejects_bad_input(client):
    # duplicate username
    _new(client, full_name="A", role="barista", phone="+998901234500",
         username="dup", password="pass1234", pin="1111")
    r = _new(client, full_name="B", role="owner", phone="+998901234501",
             username="dup", password="pass1234")
    assert r.status_code == 400

    cases = [
        dict(full_name="X", role="barista", phone="+998901112255", username="z1", pin="1111"),          # no password
        dict(full_name="X", role="owner", phone="+998901112266", username="z2", password="123"),         # short pass
        dict(full_name="X", role="owner", phone="bogus", username="z3", password="pass1234"),            # bad phone
        dict(full_name="X", role="barista", phone="+998901112277", username="z4", password="pass1234"),  # no pin
        dict(full_name="X", role="owner", phone="+998901112288", password="pass1234"),                   # no username
    ]
    for data in cases:
        assert _new(client, **data).status_code == 400


@pytest.mark.asyncio
async def test_login_by_username(ctx, client):
    _new(client, full_name="Own", role="owner", phone="998935551122",
         username="own2", password="pass5678")

    ok = client.post("/admin/login", data={"username": "own2", "password": "pass5678"},
                     follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/admin"

    bad = client.post("/admin/login", data={"username": "own2", "password": "nope"},
                      follow_redirects=False)
    assert bad.status_code == 401

    # A barista must not be able to log into the web admin.
    _new(client, full_name="Bar", role="barista", phone="+998901234567",
         username="bar1", password="pass1234", pin="4321")
    blocked = client.post("/admin/login", data={"username": "bar1", "password": "pass1234"},
                          follow_redirects=False)
    assert blocked.status_code == 401
