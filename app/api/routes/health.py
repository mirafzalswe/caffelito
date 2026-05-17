"""Liveness + readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
    redis = get_redis()
    pong = await redis.ping()
    return {"db": "ok", "redis": "ok" if pong else "fail"}
