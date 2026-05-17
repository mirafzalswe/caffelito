from __future__ import annotations

from app.core.security import (
    hash_secret,
    random_redeem_code,
    random_token,
    verify_secret,
)


def test_hash_and_verify_pin():
    h = hash_secret("1234")
    assert verify_secret(h, "1234")
    assert not verify_secret(h, "1235")


def test_random_redeem_code_shape():
    code = random_redeem_code(6)
    assert len(code) == 6 and code.isdigit()


def test_random_token_unique():
    a, b = random_token(), random_token()
    assert a != b and len(a) > 30
