"""Pure-unit tests — no DB needed."""

from __future__ import annotations

import pytest

from app.core.phone import InvalidPhoneError, mask_phone, normalize_phone


def test_normalize_phone_e164():
    assert normalize_phone("+998 90 123 45 67") == "+998901234567"
    assert normalize_phone("+1-415-555-2671") == "+14155552671"


def test_normalize_phone_invalid():
    with pytest.raises(InvalidPhoneError):
        normalize_phone("")
    with pytest.raises(InvalidPhoneError):
        normalize_phone("123")


def test_mask_phone():
    assert mask_phone("+998901234567") == "+9989***4567"
    assert mask_phone("") == "***"
