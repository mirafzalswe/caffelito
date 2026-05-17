"""Async SQLAlchemy engine and session factory.

Usage in service code:

    async with session_scope() as session:
        ...                 # work
        # commit/rollback handled by the context manager

Inside FastAPI endpoints prefer the dependency ``get_session``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _build_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine: AsyncEngine = _build_engine()
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def session_scope(*, tenant_id: str | None = None) -> AsyncIterator[AsyncSession]:
    """Open a session, set the RLS tenant, and commit/rollback on exit.

    The ``tenant_id`` is propagated to ``app.tenant_id`` GUC so RLS policies
    on tenant-scoped tables enforce isolation. Pass ``None`` only for
    cross-tenant operations (system jobs).
    """
    async with SessionLocal() as session:
        try:
            if tenant_id is not None:
                await session.execute(
                    _set_tenant_stmt(),
                    {"tid": tenant_id},
                )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _set_tenant_stmt():  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    return text("SELECT set_config('app.tenant_id', :tid, true)")


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
