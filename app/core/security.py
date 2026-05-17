"""Password / PIN hashing using argon2id with an application-wide pepper."""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()


def _pepper(value: str) -> str:
    """HMAC the value with the pepper before argon2.

    Argon2 already salts. The pepper is an application-wide secret that lives
    outside the DB; an attacker with a DB dump still can't brute-force without it.
    """
    pepper = settings.security_pepper.get_secret_value().encode()
    mac = hmac.new(pepper, value.encode(), sha256).hexdigest()
    return mac


def hash_secret(value: str) -> str:
    """Hash a password / PIN."""
    return _hasher.hash(_pepper(value))


def verify_secret(stored_hash: str, value: str) -> bool:
    try:
        return _hasher.verify(stored_hash, _pepper(value))
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def random_redeem_code(digits: int = 6) -> str:
    """Short numeric code for free-coffee/prepaid redemption shown to barista."""
    return "".join(secrets.choice("0123456789") for _ in range(digits))
