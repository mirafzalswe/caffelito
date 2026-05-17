"""Broadcasts: owner-driven push messages with optional photo/video to all
linked Telegram customers of the tenant.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app import __version__
from app.admin.deps import CurrentAdminDep, CurrentTenantDep, SessionDep
from app.admin.templating import templates
from app.domain.audit import record_audit
from app.domain.broadcast import count_eligible_recipients, dispatch
from app.models import Broadcast

router = APIRouter(prefix="/broadcasts")


# Media is stored in a project-local directory so the file is reachable from
# the long-running dispatch task. `static/broadcasts/` keeps it next to other
# admin assets; admin auth gates uploads, the URL is only used internally by
# the bot when calling Telegram.
_MEDIA_ROOT = Path(__file__).resolve().parents[1] / "static" / "broadcasts"
_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
_MAX_BYTES = 50 * 1024 * 1024  # 50MB — matches Telegram bot video limit


def _can_manage(role: str) -> bool:
    return role == "owner"


def _detect_media(file: UploadFile | None) -> tuple[str | None, str | None]:
    """Return ``(media_type, suffix)`` or ``(None, None)`` if no usable file."""
    if not file or not file.filename:
        return None, None
    suffix = Path(file.filename).suffix.lower()
    if suffix in _PHOTO_EXT:
        return "photo", suffix
    if suffix in _VIDEO_EXT:
        return "video", suffix
    return None, None


@router.get("/", response_class=HTMLResponse)
async def list_broadcasts(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    rows = (await db.execute(
        select(Broadcast)
        .where(Broadcast.tenant_id == tenant.id)
        .order_by(Broadcast.created_at.desc())
        .limit(50)
    )).scalars().all()
    recipients = await count_eligible_recipients(db, tenant_id=tenant.id)
    return templates.TemplateResponse(
        request, "broadcasts_list.html",
        {
            "section": "broadcasts",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "rows": rows,
            "recipients": recipients,
            "can_manage": _can_manage(admin.role),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    recipients = await count_eligible_recipients(db, tenant_id=tenant.id)
    return templates.TemplateResponse(
        request, "broadcast_form.html",
        {
            "section": "broadcasts",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "recipients": recipients,
        },
    )


@router.post("/new")
async def create_and_send(
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
    body: str = Form(...),
    media: UploadFile | None = File(default=None),
) -> RedirectResponse:
    if not _can_manage(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    body = body.strip()
    if not body:
        raise HTTPException(400, "Сообщение не может быть пустым")

    bcast = Broadcast(
        tenant_id=tenant.id,
        body=body,
        status="sending",
        created_by=admin.id,
    )
    db.add(bcast)
    await db.flush()

    media_type, suffix = _detect_media(media)
    if media_type and media and suffix:
        # Stream-save the upload, enforcing the size limit.
        target = _MEDIA_ROOT / f"{bcast.id}{suffix}"
        size = 0
        with target.open("wb") as fh:
            while chunk := await media.read(1024 * 64):
                size += len(chunk)
                if size > _MAX_BYTES:
                    fh.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(400, "Файл превышает 50 МБ")
                fh.write(chunk)
        bcast.media_path = str(target)
        bcast.media_type = media_type

    await record_audit(
        db,
        tenant_id=tenant.id,
        actor_type="staff",
        actor_id=admin.id,
        action="broadcast.send",
        target_type="broadcast",
        target_id=bcast.id,
        after={
            "body_preview": body[:120],
            "media_type": bcast.media_type,
        },
    )
    await db.commit()

    # Fire-and-forget dispatch — the request returns immediately, dispatch
    # streams progress into the same row via its own short sessions.
    asyncio.create_task(dispatch(bcast.id))

    return RedirectResponse(f"/admin/broadcasts/{bcast.id}", status_code=303)


@router.get("/{broadcast_id}", response_class=HTMLResponse)
async def detail(
    request: Request,
    broadcast_id: uuid.UUID,
    db: SessionDep,
    admin: CurrentAdminDep,
    tenant: CurrentTenantDep,
) -> HTMLResponse:
    bcast = (await db.execute(
        select(Broadcast).where(
            Broadcast.id == broadcast_id, Broadcast.tenant_id == tenant.id
        )
    )).scalar_one_or_none()
    if bcast is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(
        request, "broadcast_detail.html",
        {
            "section": "broadcasts",
            "admin": admin,
            "tenant_name": tenant.name,
            "app_version": __version__,
            "b": bcast,
        },
    )
