"""Customer bot handler registration."""

from aiogram import Router

from app.bots.customer.handlers import dashboard, history, lang, redeem, start


def build_router() -> Router:
    root = Router(name="customer")
    root.include_routers(
        start.router,
        dashboard.router,
        history.router,
        redeem.router,
        lang.router,
    )
    return root
