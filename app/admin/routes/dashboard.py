"""Dashboard — KPIs + live transaction feed (htmx polling)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from app import __version__
from app.admin.deps import (
    CurrentAdminDep,
    CurrentTenantDep,
    SessionDep,
)
from app.admin.templating import templates
from app.core.clock import now
from app.models import Branch, Transaction, User

router = APIRouter()


async def _kpis(db, *, tenant_id) -> dict[str, Any]:
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    customers_total = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
        )
    ).scalar_one()

    active_30d = (
        await db.execute(
            select(func.count(func.distinct(Transaction.user_id)))
            .where(
                Transaction.tenant_id == tenant_id,
                Transaction.created_at >= today_start - timedelta(days=30),
            )
        )
    ).scalar_one()

    tx_today = (
        await db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.tenant_id == tenant_id,
                Transaction.created_at >= today_start,
            )
        )
    ).scalar_one()

    revenue_7d = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.total_amount), 0))
            .where(
                Transaction.tenant_id == tenant_id,
                Transaction.type == "purchase",
                Transaction.created_at >= week_start,
            )
        )
    ).scalar_one()

    free_redeems_7d = (
        await db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.tenant_id == tenant_id,
                Transaction.type == "redeem_free",
                Transaction.created_at >= week_start,
            )
        )
    ).scalar_one()

    prepaid_consumed_7d = (
        await db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.tenant_id == tenant_id,
                Transaction.type == "prepaid_consume",
                Transaction.created_at >= week_start,
            )
        )
    ).scalar_one()

    # VIP deposits the shop still "owes" to customers (live commitment).
    from app.models import Membership

    vip_count = (
        await db.execute(
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == tenant_id, Membership.status == "active")
        )
    ).scalar_one()
    vip_liability = (
        await db.execute(
            select(func.coalesce(func.sum(Membership.balance_remaining), 0))
            .where(Membership.tenant_id == tenant_id, Membership.status == "active")
        )
    ).scalar_one()

    return {
        "customers_total": customers_total,
        "active_30d": active_30d,
        "tx_today": tx_today,
        "revenue_7d": revenue_7d,
        "free_redeems_7d": free_redeems_7d,
        "prepaid_consumed_7d": prepaid_consumed_7d,
        "vip_count": vip_count,
        "vip_liability": vip_liability,
    }


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    kpis = await _kpis(db, tenant_id=tenant.id)
    branches_count = (
        await db.execute(
            select(func.count())
            .select_from(Branch)
            .where(Branch.tenant_id == tenant.id, Branch.status == "active")
        )
    ).scalar_one()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "section": "dashboard",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "kpis": kpis,
            "branches_count": branches_count,
        },
    )


@router.get("/feed", response_class=HTMLResponse)
async def feed(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    """Partial — htmx-polled every 5s for the live transaction feed."""
    rows = (
        await db.execute(
            select(Transaction)
            .where(Transaction.tenant_id == tenant.id)
            .order_by(Transaction.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "partials/tx_feed.html",
        {"rows": rows},
    )
