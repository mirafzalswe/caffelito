"""Campaigns CRUD with JSON-rules editor."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.core.clock import now
from app.domain.audit import record_audit
from app.models import Branch, Campaign, CampaignBranch
from app.models.campaign import CAMPAIGN_TYPES

router = APIRouter(prefix="/campaigns")


def _can_manage(role: str) -> bool:
    return role == "owner"


@router.get("/", response_class=HTMLResponse)
async def list_campaigns(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    rows = (
        await db.execute(
            select(Campaign)
            .where(Campaign.tenant_id == tenant.id)
            .order_by(Campaign.created_at.desc())
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "campaigns_list.html",
        {
            "section": "campaigns",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "can_manage": _can_manage(admin.role),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    branches = (
        await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.status == "active")
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "campaign_form.html",
        {
            "section": "campaigns",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "campaign": None,
            "branches": branches,
            "selected_branches": set(),
            "campaign_types": CAMPAIGN_TYPES,
            "rules_json": json.dumps(
                {
                    "type": "punchcard",
                    "trigger": {
                        "product_category": "coffee",
                        "loyalty_eligible_only": True,
                    },
                    "stamps_required": 10,
                    "expires_after_days": 90,
                    "cooldown_minutes": 0,
                },
                indent=2,
                ensure_ascii=False,
            ),
        },
    )


@router.post("/new")
async def create(
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    code: str = Form(...),
    name: str = Form(...),
    type: str = Form(...),
    rules: str = Form(...),
    status_: str = Form(alias="status", default="draft"),
    branches: list[uuid.UUID] = Form(default=[]),
    priority: int = Form(default=100),
    stackable: str | None = Form(default=None),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        rules_obj = json.loads(rules)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Невалидный JSON в rules: {exc}") from exc

    camp = Campaign(
        tenant_id=tenant.id,
        code=code.strip(),
        name=name.strip(),
        type=type,
        status=status_,
        rules=rules_obj,
        priority=max(0, min(int(priority), 1000)),
        stackable=stackable is not None,
        created_by=admin.id,
    )
    db.add(camp)
    await db.flush()

    for bid in branches:
        db.add(CampaignBranch(campaign_id=camp.id, branch_id=bid))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="campaign.create",
        target_type="campaign",
        target_id=camp.id,
        after={
            "code": code,
            "name": name,
            "type": type,
            "status": status_,
            "priority": camp.priority,
            "stackable": camp.stackable,
        },
    )
    await db.commit()
    return RedirectResponse(f"/admin/campaigns/{camp.id}?created=1", status_code=303)


@router.get("/{campaign_id}", response_class=HTMLResponse)
async def detail(
    request: Request,
    campaign_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    camp = (
        await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id, Campaign.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if camp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    branches = (
        await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id)
        )
    ).scalars().all()
    selected = {
        cb.branch_id
        for cb in (
            await db.execute(
                select(CampaignBranch).where(CampaignBranch.campaign_id == camp.id)
            )
        ).scalars()
    }

    flash = None
    if request.query_params.get("created"):
        flash = f"✅ Акция «{camp.name}» создана."
    elif request.query_params.get("saved"):
        flash = f"✅ Изменения акции «{camp.name}» сохранены."

    return templates.TemplateResponse(
        request,
        "campaign_form.html",
        {
            "section": "campaigns",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "campaign": camp,
            "branches": branches,
            "selected_branches": selected,
            "campaign_types": CAMPAIGN_TYPES,
            "rules_json": json.dumps(camp.rules, indent=2, ensure_ascii=False),
            "can_manage": _can_manage(admin.role),
            "flash": flash,
            "flash_kind": "success" if flash else None,
        },
    )


@router.post("/{campaign_id}")
async def update(
    campaign_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    name: str = Form(...),
    rules: str = Form(...),
    status_: str = Form(alias="status"),
    branches: list[uuid.UUID] = Form(default=[]),
    priority: int = Form(default=100),
    stackable: str | None = Form(default=None),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    camp = (
        await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id, Campaign.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if camp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    try:
        rules_obj = json.loads(rules)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Невалидный JSON в rules: {exc}") from exc

    before = {
        "name": camp.name,
        "status": camp.status,
        "rules": camp.rules,
        "priority": camp.priority,
        "stackable": camp.stackable,
    }
    camp.name = name.strip()
    camp.status = status_
    camp.rules = rules_obj
    camp.priority = max(0, min(int(priority), 1000))
    camp.stackable = stackable is not None
    camp.updated_at = now()

    # Replace branches
    await db.execute(
        CampaignBranch.__table__.delete().where(
            CampaignBranch.campaign_id == camp.id
        )
    )
    for bid in branches:
        db.add(CampaignBranch(campaign_id=camp.id, branch_id=bid))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="campaign.update",
        target_type="campaign",
        target_id=camp.id,
        before=before,
        after={
            "name": name,
            "status": status_,
            "rules": rules_obj,
            "priority": camp.priority,
            "stackable": camp.stackable,
        },
    )
    await db.commit()
    return RedirectResponse(f"/admin/campaigns/{campaign_id}?saved=1", status_code=303)
