"""FastAPI dependencies for the admin panel."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import read_session
from app.core.db import get_session
from app.models import Staff, Tenant


SessionDep = Annotated[AsyncSession, Depends(get_session)]


class AuthRedirect(HTTPException):
    """Internal sentinel — middleware returns RedirectResponse for it."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_307_TEMPORARY_REDIRECT)


async def current_admin(
    request: Request,
    db: SessionDep,
) -> Staff:
    payload = read_session(request)
    if payload is None:
        raise AuthRedirect()
    stmt = select(Staff).where(Staff.id == payload.staff_id, Staff.status == "active")
    staff = (await db.execute(stmt)).scalar_one_or_none()
    if staff is None or staff.role != "owner":
        raise AuthRedirect()
    return staff


CurrentAdminDep = Annotated[Staff, Depends(current_admin)]


async def current_tenant(
    db: SessionDep,
    admin: CurrentAdminDep,
) -> Tenant:
    stmt = select(Tenant).where(Tenant.id == admin.tenant_id)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if tenant is None:
        raise AuthRedirect()
    return tenant


CurrentTenantDep = Annotated[Tenant, Depends(current_tenant)]


def require_role(*allowed: str):
    """Decorator-style dep factory: 403 unless admin.role is in ``allowed``."""

    async def _checker(admin: CurrentAdminDep) -> Staff:
        if admin.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return admin

    return _checker
