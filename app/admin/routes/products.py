"""Products CRUD."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.domain.audit import record_audit
from app.models import Product

router = APIRouter(prefix="/products")


def _can_manage(role: str) -> bool:
    return role == "owner"


@router.get("/", response_class=HTMLResponse)
async def list_products(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    rows = (
        await db.execute(
            select(Product)
            .where(Product.tenant_id == tenant.id)
            .order_by(Product.name, Product.size)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "products_list.html",
        {
            "section": "products",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "can_manage": _can_manage(admin.role),
        },
    )


@router.post("/new")
async def create_product(
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    name: str = Form(...),
    base_price: str = Form(...),
    sku: str = Form(""),
    category: str = Form(""),
    size: str = Form(""),
    is_loyalty_eligible: str = Form("on"),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        price = Decimal(base_price.replace(",", "."))
        if price < 0:
            raise InvalidOperation
    except InvalidOperation as exc:
        raise HTTPException(400, "Невалидная цена") from exc

    p = Product(
        tenant_id=tenant.id,
        sku=sku.strip() or None,
        name=name.strip(),
        category=category.strip() or None,
        size=size.strip() or None,
        base_price=price,
        is_loyalty_eligible=(is_loyalty_eligible == "on"),
        is_active=True,
    )
    db.add(p)
    await db.flush()

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="product.create",
        target_type="product",
        target_id=p.id,
        after={
            "sku": sku,
            "name": name,
            "category": category,
            "size": size,
            "base_price": str(price),
        },
    )
    await db.commit()
    return RedirectResponse("/admin/products/", status_code=303)


@router.post("/{product_id}/toggle")
async def toggle_product(
    product_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    p = (
        await db.execute(
            select(Product).where(
                Product.id == product_id, Product.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    before = {"is_active": p.is_active}
    p.is_active = not p.is_active
    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="product.toggle_active",
        target_type="product",
        target_id=p.id,
        before=before,
        after={"is_active": p.is_active},
    )
    await db.commit()
    return RedirectResponse("/admin/products/", status_code=303)
