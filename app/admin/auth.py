"""Cookie-based session auth for the admin panel.

Implementation choices:

* Session lives in a signed (HMAC) cookie via ``itsdangerous`` — no DB row
  per session, fine for the expected admin volume.
* Cookie holds only ``(staff_id, tenant_id, expires_at)``; the actual staff
  record is loaded fresh on every request via ``current_admin``.
* TTL = 8 hours by default. Renewed on each successful request to slide the
  expiry forward.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from fastapi import Request, Response

try:
    # itsdangerous v2.x
    from itsdangerous import BadSignature, TimestampSigner
except Exception:  # noqa: BLE001
    raise

from app.core.config import settings

COOKIE_NAME = "coffee_admin_sid"
SESSION_TTL = 8 * 60 * 60  # 8 hours


def _signer() -> TimestampSigner:
    return TimestampSigner(settings.jwt_secret.get_secret_value())


@dataclass(slots=True)
class SessionPayload:
    staff_id: uuid.UUID
    tenant_id: uuid.UUID
    issued_at: int


def encode_session(*, staff_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    raw = f"{staff_id}:{tenant_id}:{int(time.time())}".encode()
    return _signer().sign(raw).decode()


def decode_session(token: str) -> SessionPayload | None:
    try:
        raw = _signer().unsign(token.encode(), max_age=SESSION_TTL).decode()
    except BadSignature:
        return None
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    try:
        return SessionPayload(
            staff_id=uuid.UUID(parts[0]),
            tenant_id=uuid.UUID(parts[1]),
            issued_at=int(parts[2]),
        )
    except (ValueError, TypeError):
        return None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="strict",
        secure=settings.is_prod,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def read_session(request: Request) -> SessionPayload | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    return decode_session(raw)
