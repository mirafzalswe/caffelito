"""Login / logout."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app import __version__
from app.admin.auth import (
    clear_session_cookie,
    encode_session,
    set_session_cookie,
)
from app.admin.deps import SessionDep
from app.admin.templating import templates
from app.core.security import verify_secret
from app.models import Staff

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_version": __version__, "error": error},
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    db: SessionDep,
    username: str = Form(...),
    password: str = Form(...),
):
    username = username.strip()
    stmt = select(Staff).where(Staff.username == username, Staff.status == "active")
    staff = (await db.execute(stmt)).scalar_one_or_none()

    invalid = (
        staff is None
        or staff.password_hash is None
        or not verify_secret(staff.password_hash, password)
        or staff.role != "owner"
    )
    if invalid:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "app_version": __version__,
                "error": "Неверный логин или пароль.",
                "username": username,
            },
            status_code=401,
        )

    token = encode_session(staff_id=staff.id, tenant_id=staff.tenant_id)
    response = RedirectResponse(url="/admin", status_code=303)
    set_session_cookie(response, token)
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/admin/login", status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/lang/{code}")
async def set_lang(request: Request, code: str) -> RedirectResponse:
    """Persist the admin UI language in a cookie and bounce back."""
    from app.core.i18n import LANGUAGES

    if code not in LANGUAGES:
        code = "ru"
    referer = request.headers.get("referer") or "/admin/"
    response = RedirectResponse(url=referer, status_code=303)
    # 1 year cookie, scoped to /admin
    response.set_cookie(
        "admin_lang", code,
        max_age=60 * 60 * 24 * 365, path="/admin", samesite="lax"
    )
    return response
