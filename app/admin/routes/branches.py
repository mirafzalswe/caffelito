"""Branches list + simple create form."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.domain.audit import record_audit
from app.models import Branch, Transaction

router = APIRouter(prefix="/branches")


@router.get("/", response_class=HTMLResponse)
async def list_branches(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    edit: uuid.UUID | None = None,
) -> HTMLResponse:
    rows = (
        await db.execute(
            select(Branch)
            .where(Branch.tenant_id == tenant.id)
            .order_by(Branch.name)
        )
    ).scalars().all()
    editing = None
    if edit is not None:
        editing = next((b for b in rows if b.id == edit), None)
    return templates.TemplateResponse(
        request,
        "branches_list.html",
        {
            "section": "branches",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "editing": editing,
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


@router.post("/{branch_id}/edit")
async def edit_branch(
    branch_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    name: str = Form(...),
    address: str = Form(""),
    timezone: str = Form("Asia/Tashkent"),
) -> RedirectResponse:
    if admin.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    b = (
        await db.execute(
            select(Branch).where(Branch.id == branch_id, Branch.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    before = {"name": b.name, "address": b.address, "timezone": b.timezone}
    b.name = name.strip()
    b.address = address.strip() or None
    b.timezone = timezone.strip()
    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="branch.update",
        target_type="branch",
        target_id=b.id,
        before=before,
        after={"name": b.name, "address": b.address, "timezone": b.timezone},
    )
    await db.commit()
    return RedirectResponse("/admin/branches", status_code=303)


@router.post("/{branch_id}/toggle")
async def toggle_branch(
    branch_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> RedirectResponse:
    """Open/close a branch (soft). Closed branches drop out of pickers."""
    if admin.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    b = (
        await db.execute(
            select(Branch).where(Branch.id == branch_id, Branch.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    before = b.status
    b.status = "closed" if b.status == "active" else "active"
    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="branch.toggle_status",
        target_type="branch",
        target_id=b.id,
        before={"status": before},
        after={"status": b.status},
    )
    await db.commit()
    return RedirectResponse("/admin/branches", status_code=303)


@router.post("/{branch_id}/delete")
async def delete_branch(
    branch_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> RedirectResponse:
    """Delete a branch. Hard-delete only if no transaction ran there;
    otherwise close it (history references the branch)."""
    if admin.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    b = (
        await db.execute(
            select(Branch).where(Branch.id == branch_id, Branch.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    used = (
        await db.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.branch_id == branch_id
            )
        )
    ).scalar()

    if used:
        b.status = "closed"
        action = "branch.close"
    else:
        await db.delete(b)
        action = "branch.delete"

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action=action,
        target_type="branch",
        target_id=branch_id,
        before={"name": b.name, "status": b.status},
    )
    await db.commit()
    return RedirectResponse("/admin/branches", status_code=303)
