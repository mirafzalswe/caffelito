"""Customers list + detail + manual admin actions.

Admin actions per ТЗ:
- create customer by phone
- record purchase
- grant bonus (free coffee / cashback / stamps)
- open prepaid package
- block / unblock
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.core.phone import InvalidPhoneError, normalize_phone
from app.core.security import random_token
import asyncio

from app.domain import bonus as bonus_svc
from app.domain import customer_notify as notify_svc
from app.domain import identity, prepaid as prepaid_svc
from app.domain import membership as membership_svc
from app.domain import redeem as redeem_svc
from app.domain.audit import record_audit
from app.domain.dashboard import read_dashboard, recent_transactions
from app.domain.errors import DomainError, FreeCoffeeExpired, FreeCoffeeNotAvailable
from app.domain.loyalty_engine import record_purchase
from app.domain.schemas import PurchaseLine, PurchaseRequest
from app.models import (
    Branch,
    Campaign,
    LoyaltyCard,
    Membership,
    PrepaidPackage,
    Product,
    Transaction,
    User,
)

router = APIRouter(prefix="/customers")


def _can_manage(role: str) -> bool:
    return role == "owner"


def _accept_crid(received: str | None, namespace: str) -> str:
    """Use the form-supplied idempotency key if it looks valid; else generate
    a fresh one. Validates length and char-set so a malformed/long string can't
    blow past the column constraint or be used as a probe vector.
    """
    s = (received or "").strip()
    if 8 <= len(s) <= 100 and all(c.isalnum() or c in ":-_." for c in s):
        return s
    return f"adm-{namespace}:{random_token(16)}"


# ---------------------------------------------------------------------------
# List + search
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def list_customers(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    q: str | None = None,
    page: int = 1,
) -> HTMLResponse:
    from sqlalchemy import or_

    per_page = 30
    page = max(1, page)
    base = select(User).where(
        User.tenant_id == tenant.id, User.deleted_at.is_(None)
    )
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        like = f"%{q}%"
        clauses = [User.full_name.ilike(like)]
        if digits:
            clauses.append(User.phone_e164.like(f"%{digits}%"))
        base = base.where(or_(*clauses))
    rows = (
        await db.execute(
            base.order_by(User.created_at.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "customers_list.html",
        {
            "section": "customers",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "q": q or "",
            "page": page,
            "has_next": len(rows) == per_page,
            "can_manage": _can_manage(admin.role),
        },
    )


# ---------------------------------------------------------------------------
# Create customer by phone
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
async def new_customer_form(
    request: Request,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request,
        "customer_new.html",
        {
            "section": "customers",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
        },
    )


@router.post("/new", response_model=None)
async def create_customer(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    phone: str = Form(...),
    full_name: str = Form(""),
):
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        normalized = normalize_phone(phone)
    except InvalidPhoneError as exc:
        return templates.TemplateResponse(
            request,
            "customer_new.html",
            {
                "section": "customers",
                "admin": admin,
                "tenant_name": tenant.name,
                "app_version": __version__,
                "error": f"Невалидный номер: {exc}",
                "phone": phone,
                "full_name": full_name,
            },
            status_code=400,
        )

    user, created = await identity.find_or_create_by_phone(
        db,
        tenant_id=tenant.id,
        phone=normalized,
        full_name=full_name.strip() or None,
        source="admin",
    )
    if created:
        await record_audit(
            db,
            tenant_id=tenant.id,
            actor_type="staff",
            actor_id=admin.id,
            action="user.create",
            target_type="user",
            target_id=user.id,
            after={"phone": normalized, "full_name": full_name},
        )
    await db.commit()
    return RedirectResponse(f"/admin/customers/{user.id}", status_code=303)


# ---------------------------------------------------------------------------
# Detail + actions
# ---------------------------------------------------------------------------


async def _load_user(db, user_id, tenant_id):
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Клиент не найден")
    return user


_OK_FLASH = {
    "purchase": "✅ Покупка начислена.",
    "bonus":    "✅ Бонус выдан.",
    "prepaid":  "✅ Пакет открыт.",
    "blocked":  "🚫 Клиент заблокирован.",
    "unblocked":"✅ Клиент разблокирован.",
    "created":  "✅ Клиент создан.",
}


@router.get("/{user_id}", response_class=HTMLResponse)
async def detail(
    request: Request,
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    user = await _load_user(db, user_id, tenant.id)
    view = await read_dashboard(db, user_id=user.id)
    txs = await recent_transactions(db, user_id=user.id, limit=20)

    active_packages = (
        await db.execute(
            select(PrepaidPackage, Campaign.name)
            .join(Campaign, Campaign.id == PrepaidPackage.campaign_id, isouter=True)
            .where(
                PrepaidPackage.user_id == user.id,
                PrepaidPackage.status == "active",
                PrepaidPackage.qty_remaining > 0,
            )
            .order_by(PrepaidPackage.expires_at.asc().nullslast())
        )
    ).all()

    active_cards = (
        await db.execute(
            select(LoyaltyCard, Campaign.name)
            .join(Campaign, Campaign.id == LoyaltyCard.campaign_id)
            .where(
                LoyaltyCard.user_id == user.id,
                LoyaltyCard.status.in_(("open", "complete")),
            )
            .order_by(LoyaltyCard.status.desc(), LoyaltyCard.opened_at.asc())
        )
    ).all()

    # Lifetime counter — how many free coffees the customer has actually
    # received. Grows by 1 on every successful redeem and is visible even
    # when ``free_coffees_available == 0``.
    total_redeemed = (
        await db.execute(
            select(func.count(LoyaltyCard.id)).where(
                LoyaltyCard.user_id == user.id,
                LoyaltyCard.status == "redeemed",
            )
        )
    ).scalar_one()

    # Lifetime spend — sum of committed paid purchases. Refunds are tracked
    # as a separate tx type so they don't double-subtract here; we just show
    # the gross "money brought to the shop".
    lifetime_spend = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.total_amount), 0)).where(
                Transaction.user_id == user.id,
                Transaction.type == "purchase",
                Transaction.status == "committed",
            )
        )
    ).scalar_one()

    # Show every campaign the admin has created (except archived) so the list
    # matches /admin/campaigns/ exactly. Inactive ones are tagged in the UI
    # and the backend still refuses to write to non-active ones.
    # Campaigns shown in the "Purchase → which campaign to apply" dropdown.
    # Both punchcard AND cashback are applicable at purchase time. VIP
    # (tiered_status) is excluded — it's activated separately in its own tab.
    # Inactive non-archived rows are still listed (disabled in the UI) so the
    # admin understands why an option isn't usable.
    punchcard_campaigns = (
        await db.execute(
            select(Campaign)
            .where(
                Campaign.tenant_id == tenant.id,
                Campaign.type.in_(("punchcard", "cashback")),
                Campaign.status != "archived",
            )
            .order_by(
                (Campaign.status == "active").desc(),
                Campaign.type,
                Campaign.priority.desc(),
                Campaign.name,
            )
        )
    ).scalars().all()

    # Tier (VIP membership) campaigns — for the activation form.
    tier_campaigns = (
        await db.execute(
            select(Campaign)
            .where(
                Campaign.tenant_id == tenant.id,
                Campaign.type == "tiered_status",
                Campaign.status == "active",
            )
            .order_by(Campaign.priority.desc(), Campaign.name)
        )
    ).scalars().all()

    # Active VIP membership (if any) for the KPI card.
    active_membership = await membership_svc.get_active_membership(
        db, tenant_id=tenant.id, user_id=user.id
    )
    active_membership_name: str | None = None
    if active_membership is not None:
        active_membership_name = (
            await db.execute(
                select(Campaign.name).where(Campaign.id == active_membership.campaign_id)
            )
        ).scalar_one_or_none()

    # Last VIP membership the customer ever had — used to detect "ran out,
    # offer top-up" state and to suggest the same amount the customer paid
    # before. Newest row first.
    from app.models import Membership

    last_membership = (await db.execute(
        select(Membership)
        .where(Membership.user_id == user.id)
        .order_by(Membership.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    vip_exhausted = (
        active_membership is None
        and last_membership is not None
        and last_membership.status in ("exhausted", "expired")
    )

    branches = (
        await db.execute(
            select(Branch).where(
                Branch.tenant_id == tenant.id, Branch.status == "active"
            )
        )
    ).scalars().all()
    # Loyalty-eligible products only (бариста начисляет покупки, не аддоны/чай).
    products = (
        await db.execute(
            select(Product)
            .where(
                Product.tenant_id == tenant.id,
                Product.is_active == True,  # noqa: E712
                Product.is_loyalty_eligible == True,  # noqa: E712
            )
            .order_by(Product.name, Product.size)
        )
    ).scalars().all()

    flash = None
    flash_kind = None
    ok = request.query_params.get("ok")
    err = request.query_params.get("err")
    info = request.query_params.get("info")
    if info:
        flash = info
        flash_kind = "success"
    elif ok and ok in _OK_FLASH:
        flash = _OK_FLASH[ok]
        flash_kind = "success"
    elif err:
        flash = f"❗ {err}"
        flash_kind = ""  # default red

    # Per-form idempotency tokens — embedded as <input type=hidden> in each
    # mutating form. The same token comes back on submit, so a duplicate POST
    # (double-click, browser retry) is caught by transactions.uq_tx_idempotency
    # and only the first request takes effect.
    crids = {
        "purchase":   f"adm-purchase:{random_token(16)}",
        "bonus":      f"adm-bonus:{random_token(16)}",
        "redeem":     f"adm-redeem:{random_token(16)}",
        "membership": f"adm-membership:{random_token(16)}",
        "prepaid":    f"adm-prepaid:{random_token(16)}",
    }

    return templates.TemplateResponse(
        request,
        "customer_detail.html",
        {
            "section": "customers",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "user": user,
            "view": view,
            "txs": txs,
            "active_packages": active_packages,
            "active_cards": active_cards,
            "branches": branches,
            "products": products,
            "punchcard_campaigns": punchcard_campaigns,
            "tier_campaigns": tier_campaigns,
            "active_membership": active_membership,
            "active_membership_name": active_membership_name,
            "last_membership": last_membership,
            "vip_exhausted": vip_exhausted,
            "total_redeemed": total_redeemed,
            "lifetime_spend": lifetime_spend,
            "can_manage": _can_manage(admin.role),
            "currency": tenant.default_currency,
            "flash": flash,
            "flash_kind": flash_kind,
            "crids": crids,
        },
    )


def _back(
    uid: uuid.UUID,
    ok: str | None = None,
    err: str | None = None,
    info: str | None = None,
) -> RedirectResponse:
    from urllib.parse import quote

    qs = ""
    if info:
        qs = f"?info={quote(info)}"
    elif ok:
        qs = f"?ok={ok}"
    elif err:
        qs = f"?err={quote(err)}"
    return RedirectResponse(f"/admin/customers/{uid}{qs}", status_code=303)


@router.post("/{user_id}/block")
async def block_customer(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    reason: str = Form(""),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    user = await _load_user(db, user_id, tenant.id)
    before = {"status": user.status}
    user.status = "blocked"
    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="user.block",
        target_type="user",
        target_id=user.id,
        before=before,
        after={"status": "blocked"},
        reason=reason or None,
    )
    await db.commit()
    return _back(user_id, ok="blocked")


@router.post("/{user_id}/unblock")
async def unblock_customer(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    user = await _load_user(db, user_id, tenant.id)
    before = {"status": user.status}
    user.status = "active"
    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="user.unblock",
        target_type="user",
        target_id=user.id,
        before=before,
        after={"status": "active"},
    )
    await db.commit()
    return _back(user_id, ok="unblocked")


# ---------------------------------------------------------------------------
# Manual purchase
# ---------------------------------------------------------------------------


@router.post("/{user_id}/purchase")
async def admin_record_purchase(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    branch_id: uuid.UUID = Form(...),
    product_id: uuid.UUID = Form(...),
    qty: int = Form(1),
    campaign_id: str = Form(""),
    client_request_id: str = Form(""),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    user = await _load_user(db, user_id, tenant.id)
    if qty <= 0:
        return _back(user_id, err="Количество должно быть положительным")

    force_campaign: uuid.UUID | None = None
    if campaign_id.strip():
        try:
            force_campaign = uuid.UUID(campaign_id.strip())
        except ValueError:
            return _back(user_id, err="Невалидный ID акции")

    crid = _accept_crid(client_request_id, "purchase")
    try:
        req = PurchaseRequest(
            tenant_id=tenant.id,
            branch_id=branch_id,
            user_id=user.id,
            staff_id=admin.id,
            lines=[PurchaseLine(product_id=product_id, qty=qty, paid_with="money")],
            client_request_id=crid,
            currency=tenant.default_currency,
            source="admin_panel",
            force_campaign_id=force_campaign,
        )
        result = await record_purchase(db, request=req)
    except DomainError as exc:
        return _back(user_id, err=str(exc))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="purchase.create",
        target_type="user",
        target_id=user.id,
        after={
            "branch_id": str(branch_id),
            "product_id": str(product_id),
            "qty": qty,
            "campaign_id": str(force_campaign) if force_campaign else None,
        },
    )
    await db.commit()

    total_stamps = sum(result.stamps_added_per_card.values())

    # Fire-and-forget Telegram push to the customer — doesn't block the
    # admin's response. Errors (user blocked the bot, etc.) are swallowed
    # inside ``notify_purchase``.
    asyncio.create_task(notify_svc.notify_purchase(
        user.id,
        stamps_added=total_stamps,
        cashback_earned=result.cashback_earned,
        free_coffees_unlocked=result.free_coffees_unlocked,
        currency=tenant.default_currency,
        vip_charged=result.vip_charged,
        vip_balance_remaining=result.vip_balance_remaining,
    ))

    bits = ["✅ Покупка начислена"]
    if total_stamps > 0:
        bits.append(f"+{total_stamps} штамп(ов)")
    if result.free_coffees_unlocked:
        bits.append(f"🎁 открыт бесплатный кофе ×{result.free_coffees_unlocked}")
    if result.cashback_earned > 0:
        bits.append(f"💰 кэшбэк +{result.cashback_earned}")
    if result.vip_charged is not None:
        bits.append(f"🛡 −{result.vip_charged} с VIP")
    if (
        force_campaign is not None
        and total_stamps == 0
        and result.cashback_earned == 0
    ):
        bits.append(
            "⚠️ выбранная акция не сработала — продукт не подходит под её правила"
        )
    return _back(user_id, info=" · ".join(bits))


# ---------------------------------------------------------------------------
# Manual bonus grant
# ---------------------------------------------------------------------------


@router.post("/{user_id}/bonus")
async def admin_grant_bonus(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    branch_id: uuid.UUID = Form(...),
    kind: str = Form(...),  # 'free_coffee' | 'cashback' | 'stamps'
    qty: int = Form(0),
    amount: str = Form("0"),
    reason: str = Form(""),
    campaign_id: str = Form(""),
    client_request_id: str = Form(""),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if not reason:
        return _back(user_id, err="Укажи причину выдачи бонуса")

    user = await _load_user(db, user_id, tenant.id)
    crid = _accept_crid(client_request_id, "bonus")

    chosen_campaign: uuid.UUID | None = None
    if campaign_id.strip():
        try:
            chosen_campaign = uuid.UUID(campaign_id.strip())
        except ValueError:
            return _back(user_id, err="Невалидный ID акции")

    flash_text = "✅ Бонус выдан"
    try:
        if kind == "free_coffee":
            if qty <= 0:
                return _back(user_id, err="Количество должно быть > 0")
            if chosen_campaign is None:
                return _back(user_id, err="Выбери акцию, к которой привязать бесплатный кофе")
            flash_text = f"🎁 Выдано бесплатных кофе: {qty}"
            await bonus_svc.grant_free_coffee(
                db,
                tenant_id=tenant.id,
                branch_id=branch_id,
                user_id=user.id,
                staff_id=admin.id,
                qty=qty,
                reason=reason,
                client_request_id=crid,
                currency=tenant.default_currency,
                campaign_id=chosen_campaign,
            )
        elif kind == "stamps":
            if qty <= 0:
                return _back(user_id, err="Количество должно быть > 0")
            if chosen_campaign is None:
                return _back(user_id, err="Выбери акцию, к которой добавить штампы")
            flash_text = f"☕ Добавлено штампов: {qty}"
            await bonus_svc.grant_stamps(
                db,
                tenant_id=tenant.id,
                branch_id=branch_id,
                user_id=user.id,
                staff_id=admin.id,
                qty=qty,
                reason=reason,
                client_request_id=crid,
                currency=tenant.default_currency,
                campaign_id=chosen_campaign,
            )
        elif kind == "cashback":
            try:
                amt = Decimal(amount.replace(",", "."))
            except InvalidOperation:
                return _back(user_id, err="Невалидная сумма")
            if amt <= 0:
                return _back(user_id, err="Сумма должна быть > 0")
            flash_text = f"💰 Выдан кэшбэк: {amt} {tenant.default_currency}"
            await bonus_svc.grant_cashback(
                db,
                tenant_id=tenant.id,
                branch_id=branch_id,
                user_id=user.id,
                staff_id=admin.id,
                amount=amt,
                currency=tenant.default_currency,
                reason=reason,
                client_request_id=crid,
            )
        else:
            return _back(user_id, err=f"Неизвестный тип бонуса: {kind}")
    except DomainError as exc:
        return _back(user_id, err=str(exc))

    await db.commit()

    # Push the gift to the customer's Telegram bot.
    notify_amount = None
    if kind == "cashback":
        try:
            notify_amount = Decimal(amount.replace(",", "."))
        except InvalidOperation:
            notify_amount = None
    asyncio.create_task(notify_svc.notify_bonus_granted(
        user.id,
        kind=kind,
        qty=qty,
        amount=notify_amount,
        currency=tenant.default_currency,
    ))
    return _back(user_id, info=flash_text)


# ---------------------------------------------------------------------------
# Redeem free coffee
# ---------------------------------------------------------------------------


@router.post("/{user_id}/redeem")
async def admin_redeem_free(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    branch_id: uuid.UUID = Form(...),
    card_id: str = Form(""),
    client_request_id: str = Form(""),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    user = await _load_user(db, user_id, tenant.id)

    card_uuid: uuid.UUID | None = None
    if card_id.strip():
        try:
            card_uuid = uuid.UUID(card_id.strip())
        except ValueError:
            return _back(user_id, err="Невалидный ID карты")

    crid = _accept_crid(client_request_id, "redeem")
    try:
        await redeem_svc.redeem_free_coffee(
            db,
            tenant_id=tenant.id,
            branch_id=branch_id,
            user_id=user.id,
            staff_id=admin.id,
            product_id=None,
            client_request_id=crid,
            currency=tenant.default_currency,
            card_id=card_uuid,
        )
    except FreeCoffeeNotAvailable:
        return _back(user_id, err="У клиента нет готовых бесплатных кофе")
    except FreeCoffeeExpired:
        return _back(user_id, err="Бесплатный кофе истёк по сроку")
    except DomainError as exc:
        return _back(user_id, err=str(exc))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="redeem.free",
        target_type="user",
        target_id=user.id,
        after={"branch_id": str(branch_id), "card_id": str(card_uuid) if card_uuid else None},
    )
    await db.commit()

    # Snapshot the post-redeem counters so the flash tells the admin exactly
    # what changed: how many free coffees are still available and how many
    # the customer has ever received.
    remaining = (
        await db.execute(
            select(func.count(LoyaltyCard.id)).where(
                LoyaltyCard.user_id == user.id,
                LoyaltyCard.status == "complete",
            )
        )
    ).scalar_one()
    total_received = (
        await db.execute(
            select(func.count(LoyaltyCard.id)).where(
                LoyaltyCard.user_id == user.id,
                LoyaltyCard.status == "redeemed",
            )
        )
    ).scalar_one()
    msg = f"🎁 Бесплатный кофе выдан! Осталось: {remaining} · Всего получил: {total_received}"
    asyncio.create_task(notify_svc.notify_free_redeemed(user.id, remaining=remaining))
    return _back(user_id, info=msg)


# ---------------------------------------------------------------------------
# Open prepaid package
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Activate VIP membership
# ---------------------------------------------------------------------------


@router.post("/{user_id}/membership")
async def admin_activate_membership(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    branch_id: uuid.UUID = Form(...),
    campaign_id: uuid.UUID = Form(...),
    amount: str = Form(...),
    client_request_id: str = Form(""),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    user = await _load_user(db, user_id, tenant.id)

    try:
        amt = Decimal(amount.replace(",", "."))
        if amt <= 0:
            raise InvalidOperation
    except InvalidOperation:
        return _back(user_id, err="Невалидная сумма")

    crid = _accept_crid(client_request_id, "membership")
    try:
        m = await membership_svc.activate_membership(
            db,
            tenant_id=tenant.id,
            branch_id=branch_id,
            user_id=user.id,
            staff_id=admin.id,
            campaign_id=campaign_id,
            amount_paid=amt,
            client_request_id=crid,
            currency=tenant.default_currency,
        )
    except DomainError as exc:
        return _back(user_id, err=str(exc))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="membership.activate",
        target_type="user",
        target_id=user.id,
        after={
            "campaign_id": str(campaign_id),
            "amount_paid": str(amt),
            "discount_percent": m.discount_percent,
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
        },
    )
    await db.commit()

    expires = m.expires_at.strftime("%d.%m.%Y") if m.expires_at else "—"
    asyncio.create_task(notify_svc.notify_vip_activated(
        user.id,
        discount_percent=m.discount_percent,
        balance=m.balance_remaining,
        currency=tenant.default_currency,
    ))
    return _back(
        user_id,
        info=f"🎫 VIP-абонемент активирован: −{m.discount_percent}% до {expires}",
    )


@router.post("/{user_id}/prepaid")
async def admin_open_prepaid(
    user_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    branch_id: uuid.UUID = Form(...),
    qty: int = Form(...),
    amount: str = Form(...),
    client_request_id: str = Form(""),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    user = await _load_user(db, user_id, tenant.id)

    if qty <= 0:
        return _back(user_id, err="Количество должно быть > 0")
    try:
        amt = Decimal(amount.replace(",", "."))
        if amt < 0:
            raise InvalidOperation
    except InvalidOperation:
        return _back(user_id, err="Невалидная сумма")

    crid = _accept_crid(client_request_id, "prepaid")
    try:
        await prepaid_svc.open_package(
            db,
            tenant_id=tenant.id,
            branch_id=branch_id,
            user_id=user.id,
            staff_id=admin.id,
            qty=qty,
            amount_paid=amt,
            currency=tenant.default_currency,
            product_scope={"all_loyalty_eligible": True},
            client_request_id=crid,
        )
    except DomainError as exc:
        return _back(user_id, err=str(exc))

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="prepaid.open",
        target_type="user",
        target_id=user.id,
        after={"qty": qty, "amount": str(amt)},
    )
    await db.commit()
    return _back(user_id, ok="prepaid")
