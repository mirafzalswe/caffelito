"""Render helpers — pure functions producing display strings."""

from __future__ import annotations

from app.bots.customer import texts
from app.domain.dashboard import DashboardView


def render_dashboard(
    view: DashboardView,
    *,
    currency: str,
    lang: str = "ru",
    membership=None,
) -> str:
    if view.stamps_required > 0:
        filled = min(view.stamps_total, view.stamps_required)
        empty = max(0, view.stamps_required - filled)
        progress = texts.PROGRESS_FILLED * filled + texts.PROGRESS_EMPTY * empty
        if view.stamps_total < view.stamps_required:
            tail = texts.t("stamps_left", lang, n=view.stamps_required - view.stamps_total)
        else:
            tail = texts.t("stamps_full", lang)
        stamps_line = f"{view.stamps_total} / {view.stamps_required}{tail}"
    else:
        progress = "—"
        stamps_line = texts.t("no_card", lang)

    if membership is not None:
        vip_block = texts.t(
            "vip_line", lang,
            pct=membership.discount_percent,
            balance=f"{membership.balance_remaining:.2f}",
            currency=currency,
        )
    else:
        vip_block = ""

    return texts.t(
        "dashboard_tpl", lang,
        progress=progress,
        stamps_line=stamps_line,
        vip_block=vip_block,
        free=view.free_coffees_available,
        cashback=f"{view.cashback_balance:.2f}",
        currency=currency,
    )
