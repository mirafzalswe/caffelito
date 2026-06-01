"""Products CRUD."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.domain.audit import record_audit
from app.models import Product, TransactionItem

router = APIRouter(prefix="/products")


def _can_manage(role: str) -> bool:
    return role == "owner"


@router.get("/", response_class=HTMLResponse)
async def list_products(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    edit: uuid.UUID | None = None,
    q: str = "",
    page: int = 1,
) -> HTMLResponse:
    editing = None
    if edit is not None:
        editing = (
            await db.execute(
                select(Product).where(
                    Product.id == edit, Product.tenant_id == tenant.id
                )
            )
        ).scalar_one_or_none()
    return await _render_list(request, db, admin, tenant, editing=editing, q=q, page=page)


_PER_PAGE = 30


async def _render_list(
    request, db, admin, tenant, *,
    error=None, editing=None, status_code=200, q="", page=1,
):
    from sqlalchemy import or_

    page = max(1, page)
    base = select(Product).where(Product.tenant_id == tenant.id)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    rows = (
        await db.execute(
            base.order_by(Product.name, Product.size)
            .limit(_PER_PAGE)
            .offset((page - 1) * _PER_PAGE)
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
            "editing": editing,
            "q": q or "",
            "page": page,
            "has_next": len(rows) == _PER_PAGE,
            "flash": error,
            "flash_kind": "" if error else None,
        },
        status_code=status_code,
    )


@router.post("/new", response_model=None)
async def create_product(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    name: str = Form(...),
    base_price: str = Form(...),
    sku: str = Form(""),
    category: str = Form(""),
    size: str = Form(""),
    is_loyalty_eligible: str = Form("on"),
):
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        price = Decimal(base_price.replace(",", "."))
        if price < 0:
            raise InvalidOperation
    except InvalidOperation:
        return await _render_list(
            request, db, admin, tenant,
            error="❗ Невалидная цена — используйте формат 2.50 или 2,50",
            status_code=400,
        )

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


@router.post("/{product_id}/edit", response_model=None)
async def edit_product(
    product_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    name: str = Form(...),
    base_price: str = Form(...),
    sku: str = Form(""),
    category: str = Form(""),
    size: str = Form(""),
    is_loyalty_eligible: str = Form(""),
):
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
    try:
        price = Decimal(base_price.replace(",", "."))
        if price < 0:
            raise InvalidOperation
    except InvalidOperation:
        return await _render_list(
            request, db, admin, tenant,
            error="❗ Невалидная цена — используйте формат 2.50 или 2,50",
            editing=p, status_code=400,
        )

    before = {"name": p.name, "base_price": str(p.base_price), "category": p.category,
              "size": p.size, "is_loyalty_eligible": p.is_loyalty_eligible}
    p.name = name.strip()
    p.base_price = price
    p.sku = sku.strip() or None
    p.category = category.strip() or None
    p.size = size.strip() or None
    p.is_loyalty_eligible = (is_loyalty_eligible == "on")

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="product.update",
        target_type="product",
        target_id=p.id,
        before=before,
        after={"name": p.name, "base_price": str(price), "category": p.category,
               "size": p.size, "is_loyalty_eligible": p.is_loyalty_eligible},
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


@router.post("/{product_id}/delete")
async def delete_product(
    product_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> RedirectResponse:
    """Delete a product. Hard-delete when it was never sold; otherwise we keep
    the row (transaction history references it) and just deactivate it so it
    disappears from pickers without breaking past receipts."""
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

    used = (
        await db.execute(
            select(func.count())
            .select_from(TransactionItem)
            .where(TransactionItem.product_id == product_id)
        )
    ).scalar()

    if used:
        p.is_active = False
        action = "product.delete_soft"
    else:
        await db.delete(p)
        action = "product.delete"

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action=action,
        target_type="product",
        target_id=product_id,
        before={"name": p.name},
    )
    await db.commit()
    return RedirectResponse("/admin/products/", status_code=303)
