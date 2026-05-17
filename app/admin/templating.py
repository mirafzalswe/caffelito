"""Jinja2 setup for the admin panel.

Single shared ``templates`` instance so handlers can simply do:

    return templates.TemplateResponse(request, "customers.html", ctx)

The wrapper auto-injects ``lang`` (read from the ``admin_lang`` cookie) and a
``t(key, **fmt)`` callable into every template context, so handlers don't have
to thread i18n state through manually.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core import i18n as _i18n
from app.core.config import settings

TEMPLATES_DIR = Path(__file__).parent / "templates"


class _AdminTemplates(Jinja2Templates):
    """Jinja templates with auto-injected ``lang`` + ``t`` helpers."""

    def TemplateResponse(self, request=None, name=None, context=None, *args, **kwargs):  # type: ignore[override]
        # Support both call styles used across the codebase:
        #   templates.TemplateResponse(request, "x.html", ctx)
        #   templates.TemplateResponse("x.html", {"request": request, ...})
        if isinstance(request, str):
            # Legacy signature: (name, context)
            ctx = name if isinstance(name, dict) else {}
            name_ = request
            req_obj = ctx.get("request")
        else:
            ctx = context or {}
            name_ = name
            req_obj = request

        if req_obj is not None:
            cookie_lang = req_obj.cookies.get("admin_lang") if hasattr(req_obj, "cookies") else None
        else:
            cookie_lang = None

        lang = ctx.get("lang") or _i18n.normalize_lang(cookie_lang)
        ctx["lang"] = lang
        ctx["t"] = lambda key, **fmt: _i18n.t(key, lang=lang, **fmt)
        ctx.setdefault("LANGUAGES", _i18n.LANGUAGES)

        if isinstance(request, str):
            return super().TemplateResponse(name_, ctx, *args, **kwargs)
        return super().TemplateResponse(req_obj, name_, ctx, *args, **kwargs)


templates = _AdminTemplates(directory=str(TEMPLATES_DIR))

# Currencies that conventionally have no minor units in display.
_INTEGER_CURRENCIES = {"UZS", "JPY", "KRW", "VND", "IDR"}


def _format_money(value) -> str:  # noqa: ANN001
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if (settings.default_currency or "").upper() in _INTEGER_CURRENCIES:
        # 19000.00  ->  "19 000"  (NBSP as thousands separator)
        return f"{int(round(f)):,}".replace(",", " ")
    return f"{f:,.2f}"


def _format_dt(value) -> str:  # noqa: ANN001
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def _short_uuid(value) -> str:  # noqa: ANN001
    s = str(value) if value else ""
    return s[:8] if len(s) >= 8 else s


def _phone_mask(value) -> str:  # noqa: ANN001
    from app.core.phone import mask_phone

    return mask_phone(str(value or ""))


templates.env.filters["money"] = _format_money
templates.env.filters["dt"] = _format_dt
templates.env.filters["short"] = _short_uuid
templates.env.filters["phonemask"] = _phone_mask
