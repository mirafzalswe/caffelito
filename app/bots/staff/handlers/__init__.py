"""Staff bot handler registration."""

from aiogram import Router

from app.bots.staff.handlers import auth, customer, prepaid, refund


def build_router() -> Router:
    root = Router(name="staff")
    root.include_routers(
        auth.router,
        customer.router,
        prepaid.router,
        refund.router,
    )
    return root
