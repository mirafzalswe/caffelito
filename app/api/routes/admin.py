"""Minimal admin REST: customers + transactions read-only.

Auth is intentionally stubbed — V2 ships full session/JWT + 2FA. For now
endpoints check a shared header secret matching SECURITY_PEPPER (rotate this
before any deploy).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.models import Transaction, User

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    if token is None or token != settings.security_pepper.get_secret_value():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "admin auth required")


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/customers", dependencies=[Depends(_require_admin)])
async def list_customers(
    session: SessionDep,
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": str(u.id),
                "phone": u.phone_e164,
                "name": u.full_name,
                "telegram_id": u.telegram_id,
                "status": u.status,
                "created_at": u.created_at.isoformat(),
            }
            for u in rows
        ]
    }


@router.get("/transactions", dependencies=[Depends(_require_admin)])
async def list_transactions(
    session: SessionDep,
    user_id: uuid.UUID | None = None,
    limit: int = Query(50, le=200),
) -> dict:
    stmt = select(Transaction).order_by(Transaction.created_at.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(Transaction.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": str(t.id),
                "type": t.type,
                "user_id": str(t.user_id),
                "branch_id": str(t.branch_id),
                "staff_id": str(t.staff_id),
                "total": str(t.total_amount),
                "currency": t.currency,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ]
    }
