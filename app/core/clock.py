"""Clock abstraction so tests can freeze time. Always UTC."""

from __future__ import annotations

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
