"""Transactions log + detail."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.models import LedgerEntry, Transaction, TransactionItem, User

router = APIRouter(prefix="/transactions")


@router.get("/", response_class=HTMLResponse)
async def list_transactions(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    type: str | None = None,
    page: int = 1,
) -> HTMLResponse:
    per_page = 50
    page = max(1, page)
    base = select(Transaction).where(Transaction.tenant_id == tenant.id)
    if type:
        base = base.where(Transaction.type == type)
    rows = (
        await db.execute(
            base.order_by(Transaction.created_at.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "transactions_list.html",
        {
            "section": "transactions",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "type_filter": type or "",
            "page": page,
            "has_next": len(rows) == per_page,
        },
    )


@router.get("/{tx_id}", response_class=HTMLResponse)
async def transaction_detail(
    request: Request,
    tx_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    tx = (
        await db.execute(
            select(Transaction).where(
                Transaction.id == tx_id, Transaction.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Транзакция не найдена")

    items = (
        await db.execute(
            select(TransactionItem).where(TransactionItem.transaction_id == tx.id)
        )
    ).scalars().all()
    ledger = (
        await db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.transaction_id == tx.id)
            .order_by(LedgerEntry.created_at)
        )
    ).scalars().all()
    customer = (
        await db.execute(
            select(User).where(
                User.id == tx.user_id, User.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "transaction_detail.html",
        {
            "section": "transactions",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "tx": tx,
            "items": items,
            "ledger": ledger,
            "customer": customer,
        },
    )
