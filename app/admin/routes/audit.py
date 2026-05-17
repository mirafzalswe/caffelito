"""Read-only audit log viewer."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.models import AuditLog

router = APIRouter(prefix="/audit")


@router.get("/", response_class=HTMLResponse)
async def list_audit(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    page: int = 1,
) -> HTMLResponse:
    per_page = 50
    page = max(1, page)
    rows = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant.id)
            .order_by(AuditLog.id.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "section": "audit",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "page": page,
            "has_next": len(rows) == per_page,
        },
    )
