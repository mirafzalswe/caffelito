"""Shared pytest fixtures.

Tests run against the same Postgres referenced in DATABASE_URL but in a
disposable schema per session — to avoid touching dev data.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# Test DB lives in a separate schema named "test_<rand>"; we set search_path
# at session level so all tables are isolated from the dev `public` schema.
TEST_SCHEMA = f"test_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _engine():
    from app.core.config import settings

    engine = create_async_engine(settings.database_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_SCHEMA}"'))
        await conn.execute(text(f'SET search_path TO "{TEST_SCHEMA}"'))
        # Apply baseline schema by piggy-backing on the alembic migration.
        # For simplicity in MVP we run alembic from python here; a real test
        # harness would prep an SQL dump up-front.
        os.environ.setdefault("PYTHONPATH", ".")
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
    await engine.dispose()


@pytest_asyncio.fixture
async def session(_engine) -> AsyncIterator[AsyncSession]:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(text(f'SET search_path TO "{TEST_SCHEMA}"'))
        yield s
        await s.rollback()
