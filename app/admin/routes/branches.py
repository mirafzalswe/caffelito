"""Branches list + simple create form."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.domain.audit import record_audit
from app.models import Branch

router = APIRouter(prefix="/branches")


@router.get("/", response_class=HTMLResponse)
async def list_branches(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    rows = (
        await db.execute(
            select(Branch)
            .where(Branch.tenant_id == tenant.id)
            .order_by(Branch.name)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "branches_list.html",
        {
            "section": "branches",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "can_manage": admin.role == "owner",
        },
    )


@router.post("/new")
async def create_branch(
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    name: str = Form(...),
    address: str = Form(""),
    timezone: str = Form("Asia/Tashkent"),
) -> RedirectResponse:
    if admin.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    b = Branch(
        tenant_id=tenant.id,
        name=name.strip(),
        address=address.strip() or None,
        timezone=timezone.strip(),
        status="active",
    )
    db.add(b)
    await db.flush()
    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="branch.create",
        target_type="branch",
        target_id=b.id,
        after={"name": name, "address": address, "timezone": timezone},
    )
    await db.commit()
    return RedirectResponse("/admin/branches", status_code=303)
