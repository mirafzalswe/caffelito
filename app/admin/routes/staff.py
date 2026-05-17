"""Staff list + create barista."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.core.security import hash_secret
from app.domain.audit import record_audit
from app.models import Branch, Staff, StaffBranch

router = APIRouter(prefix="/staff")


def _can_manage(role: str) -> bool:
    return role == "owner"


@router.get("/", response_class=HTMLResponse)
async def list_staff(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    rows = (
        await db.execute(
            select(Staff)
            .where(Staff.tenant_id == tenant.id)
            .order_by(Staff.created_at.desc())
        )
    ).scalars().all()
    branches = (
        await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.status == "active")
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "staff_list.html",
        {
            "section": "staff",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "branches": branches,
            "can_manage": _can_manage(admin.role),
        },
    )


@router.post("/new")
async def create_staff(
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    full_name: str = Form(...),
    role: str = Form(...),
    pin: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    branches: list[uuid.UUID] = Form(default=[]),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    if role not in {"owner", "barista"}:
        raise HTTPException(400, "Неверная роль")
    if role == "barista" and not pin:
        raise HTTPException(400, "Бариста должен иметь PIN")
    if role == "owner" and (not email or not password):
        raise HTTPException(400, "Email и пароль обязательны для веб-роли")

    s = Staff(
        tenant_id=tenant.id,
        full_name=full_name.strip(),
        role=role,
        status="active",
        email=(email.strip().lower() or None),
        password_hash=hash_secret(password) if password else None,
        pin_hash=hash_secret(pin) if pin else None,
    )
    db.add(s)
    await db.flush()

    for bid in branches:
        db.add(StaffBranch(staff_id=s.id, branch_id=bid))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="staff.create",
        target_type="staff",
        target_id=s.id,
        after={"role": role, "full_name": full_name},
    )
    await db.commit()
    return RedirectResponse("/admin/staff", status_code=303)
