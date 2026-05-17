"""Admin route registration."""

from fastapi import APIRouter

from app.admin.routes import (
    audit,
    branches,
    broadcasts,
    campaigns,
    customers,
    dashboard,
    login,
    products,
    staff,
    transactions,
)


def build_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin")
    router.include_router(login.router)
    router.include_router(dashboard.router)
    router.include_router(customers.router)
    router.include_router(products.router)
    router.include_router(transactions.router)
    router.include_router(campaigns.router)
    router.include_router(broadcasts.router)
    router.include_router(staff.router)
    router.include_router(branches.router)
    router.include_router(audit.router)
    return router
