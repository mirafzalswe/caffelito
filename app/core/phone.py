"""Phone number normalization to E.164 — the canonical user identity.

E.164 strips formatting and prefixes ``+<country><subscriber>``. Two clients
who share a number always produce the same string regardless of how the
barista typed it.
"""

from __future__ import annotations

import phonenumbers
from phonenumbers import NumberParseException


class InvalidPhoneError(ValueError):
    """Raised when a phone string cannot be parsed into a valid number."""


def normalize_phone(raw: str, *, default_region: str = "UZ") -> str:
    """Return the phone in E.164 (`+...`).

    ``default_region`` is used only when ``raw`` lacks the country prefix.
    The default ``UZ`` reflects the initial target geography; it can be
    overridden per tenant when calling.
    """
    if raw is None:
        raise InvalidPhoneError("phone is empty")
    raw = raw.strip()
    if not raw:
        raise InvalidPhoneError("phone is empty")
    try:
        number = phonenumbers.parse(raw, default_region)
    except NumberParseException as exc:
        raise InvalidPhoneError(f"cannot parse phone: {exc}") from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidPhoneError("invalid phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(e164: str) -> str:
    """Mask the middle for logs / UI: ``+998 90 *** ** 67``."""
    if not e164 or len(e164) < 6:
        return "***"
    return e164[:5] + "***" + e164[-4:]
