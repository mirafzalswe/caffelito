"""FastAPI entrypoint — assembles routes, lifespan, error handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.admin.deps import AuthRedirect
from app.admin.routes import build_admin_router
from app.api.routes import admin as admin_api, health, webhooks
from app.core.config import settings
from app.core.db import engine
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis
from app.domain.errors import DomainError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    log = get_logger("api")
    log.info("api_start", env=settings.app_env)
    try:
        yield
    finally:
        await engine.dispose()
        await close_redis()
        log.info("api_stop")


app = FastAPI(
    title="Coffee Loyalty API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_local else None,
    redoc_url=None,
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(admin_api.router)
app.include_router(build_admin_router())

app.mount(
    "/admin/static",
    StaticFiles(directory=str(Path(__file__).parent / "admin" / "static")),
    name="admin-static",
)


@app.exception_handler(DomainError)
async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.code, "message": str(exc)},
    )


@app.exception_handler(AuthRedirect)
async def _auth_redirect_handler(request: Request, exc: AuthRedirect) -> RedirectResponse:
    """Anyone hitting /admin/* without a valid session is redirected to /admin/login."""
    return RedirectResponse(url="/admin/login", status_code=303)
