"""Staff list + create employee (owner / barista)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.core.phone import InvalidPhoneError, normalize_phone
from app.core.security import hash_secret
from app.domain.audit import record_audit
from app.models import Branch, Staff, StaffBranch, Transaction

router = APIRouter(prefix="/staff")

MIN_PASSWORD_LEN = 6


def _can_manage(role: str) -> bool:
    return role == "owner"


async def _list_context(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    *,
    error: str | None = None,
    form: dict | None = None,
    editing: Staff | None = None,
    q: str = "",
    page: int = 1,
) -> dict:
    from sqlalchemy import or_

    per_page = 30
    page = max(1, page)
    base = select(Staff).where(Staff.tenant_id == tenant.id)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Staff.full_name.ilike(like), Staff.username.ilike(like)))
    rows = (
        await db.execute(
            base.order_by(Staff.created_at.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).scalars().all()
    branches = (
        await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.status == "active")
        )
    ).scalars().all()
    editing_branch_ids: set = set()
    if editing is not None:
        editing_branch_ids = {
            sb.branch_id
            for sb in (
                await db.execute(
                    select(StaffBranch).where(StaffBranch.staff_id == editing.id)
                )
            ).scalars()
        }
    return {
        "section": "staff",
        "admin": admin,
        "tenant_name": tenant.name,
        "app_version": __version__,
        "rows": rows,
        "branches": branches,
        "can_manage": _can_manage(admin.role),
        "error": error,
        "form": form or {},
        "editing": editing,
        "editing_branch_ids": editing_branch_ids,
        "q": q or "",
        "page": page,
        "has_next": len(rows) == per_page,
    }


@router.get("/", response_class=HTMLResponse)
async def list_staff(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    edit: uuid.UUID | None = None,
    q: str = "",
    page: int = 1,
) -> HTMLResponse:
    err = "Нельзя удалить собственную учётную запись." if request.query_params.get("err") == "self" else None
    editing = None
    if edit is not None:
        editing = (
            await db.execute(
                select(Staff).where(Staff.id == edit, Staff.tenant_id == tenant.id)
            )
        ).scalar_one_or_none()
    ctx = await _list_context(request, db, admin, tenant, error=err, editing=editing, q=q, page=page)
    return templates.TemplateResponse(request, "staff_list.html", ctx)


@router.post("/new")
async def create_staff(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    full_name: str = Form(""),
    role: str = Form(""),
    phone: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    pin: str = Form(""),
    branches: list[uuid.UUID] = Form(default=[]),
):
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    full_name = full_name.strip()
    username = username.strip()
    pin = pin.strip()

    # Preserve what the user typed so we can re-fill the form on error.
    form = {
        "full_name": full_name,
        "role": role,
        "phone": phone.strip(),
        "username": username,
    }

    async def fail(message: str) -> HTMLResponse:
        ctx = await _list_context(
            request, db, admin, tenant, error=message, form=form
        )
        return templates.TemplateResponse(
            request, "staff_list.html", ctx, status_code=400
        )

    # ── Validation (server-side, friendly) ──────────────────────────────
    if role not in {"owner", "barista"}:
        return await fail("Выберите роль сотрудника.")
    if not full_name:
        return await fail("Укажите имя сотрудника.")
    if not username:
        return await fail("Укажите username.")
    if not password:
        return await fail("Укажите пароль.")
    if len(password) < MIN_PASSWORD_LEN:
        return await fail(f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов.")

    try:
        phone_e164 = normalize_phone(phone)
    except InvalidPhoneError:
        return await fail("Неверный номер телефона. Пример: +998901234567")

    if role == "barista":
        if not (pin.isdigit() and 4 <= len(pin) <= 6):
            return await fail("PIN бариста должен состоять из 4–6 цифр.")

    # Unique username within the tenant (case-insensitive — username is CITEXT).
    exists = (
        await db.execute(
            select(func.count())
            .select_from(Staff)
            .where(Staff.tenant_id == tenant.id, Staff.username == username)
        )
    ).scalar()
    if exists:
        return await fail("Сотрудник с таким username уже существует.")

    s = Staff(
        tenant_id=tenant.id,
        full_name=full_name,
        role=role,
        status="active",
        username=username,
        phone_e164=phone_e164,
        password_hash=hash_secret(password),
        pin_hash=hash_secret(pin) if role == "barista" else None,
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
        after={"role": role, "full_name": full_name, "username": username},
    )
    await db.commit()
    return RedirectResponse("/admin/staff/", status_code=303)


@router.post("/{staff_id}/edit", response_model=None)
async def edit_staff(
    staff_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    full_name: str = Form(""),
    role: str = Form(""),
    phone: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    pin: str = Form(""),
    branches: list[uuid.UUID] = Form(default=[]),
):
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    s = (
        await db.execute(
            select(Staff).where(Staff.id == staff_id, Staff.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    full_name = full_name.strip()
    username = username.strip()
    pin = pin.strip()

    async def fail(message: str) -> HTMLResponse:
        ctx = await _list_context(request, db, admin, tenant, error=message, editing=s)
        return templates.TemplateResponse(request, "staff_list.html", ctx, status_code=400)

    if role not in {"owner", "barista"}:
        return await fail("Выберите роль сотрудника.")
    if not full_name:
        return await fail("Укажите имя сотрудника.")
    if not username:
        return await fail("Укажите username.")
    try:
        phone_e164 = normalize_phone(phone)
    except InvalidPhoneError:
        return await fail("Неверный номер телефона. Пример: +998901234567")
    # Password optional on edit; if provided, enforce length.
    if password and len(password) < MIN_PASSWORD_LEN:
        return await fail(f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов.")
    # PIN optional on edit; if provided for a barista, validate format.
    if role == "barista" and pin and not (pin.isdigit() and 4 <= len(pin) <= 6):
        return await fail("PIN бариста должен состоять из 4–6 цифр.")
    # A barista with no PIN at all can't log into the bot.
    if role == "barista" and not pin and s.pin_hash is None:
        return await fail("Укажите PIN для бариста (4–6 цифр).")

    # Username must stay unique within the tenant (excluding this staff row).
    dup = (
        await db.execute(
            select(func.count()).select_from(Staff).where(
                Staff.tenant_id == tenant.id,
                Staff.username == username,
                Staff.id != s.id,
            )
        )
    ).scalar()
    if dup:
        return await fail("Сотрудник с таким username уже существует.")

    s.full_name = full_name
    s.role = role
    s.username = username
    s.phone_e164 = phone_e164
    if password:
        s.password_hash = hash_secret(password)
    if role == "barista" and pin:
        s.pin_hash = hash_secret(pin)
    if role == "owner":
        s.pin_hash = None  # owners don't use a bot PIN

    # Replace branch assignments.
    await db.execute(
        StaffBranch.__table__.delete().where(StaffBranch.staff_id == s.id)
    )
    for bid in branches:
        db.add(StaffBranch(staff_id=s.id, branch_id=bid))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="staff.update",
        target_type="staff",
        target_id=s.id,
        after={"role": role, "full_name": full_name, "username": username},
    )
    await db.commit()
    return RedirectResponse("/admin/staff/", status_code=303)


@router.post("/{staff_id}/delete")
async def delete_staff(
    staff_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> RedirectResponse:
    """Remove an employee. Hard-delete if they never processed a transaction;
    otherwise mark them ``left`` so historical transactions keep their author.
    You cannot remove your own account."""
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if staff_id == admin.id:
        return RedirectResponse("/admin/staff/?err=self", status_code=303)

    s = (
        await db.execute(
            select(Staff).where(Staff.id == staff_id, Staff.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    used = (
        await db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.staff_id == staff_id)
        )
    ).scalar()

    if used:
        s.status = "left"
        action = "staff.deactivate"
    else:
        await db.execute(
            StaffBranch.__table__.delete().where(StaffBranch.staff_id == staff_id)
        )
        await db.delete(s)
        action = "staff.delete"

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action=action,
        target_type="staff",
        target_id=staff_id,
        before={"full_name": s.full_name, "role": s.role},
    )
    await db.commit()
    return RedirectResponse("/admin/staff/", status_code=303)
