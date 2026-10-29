"""Password hashing with Argon2id.

Only encoded hashes are stored. The plain password never leaves this module.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    """Return an Argon2id encoded hash."""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    return _hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Constant-time verification; returns False for any malformed hash."""

    try:
        return _hasher.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(encoded_hash: str) -> bool:
    """True when the hash used older parameters and should be upgraded."""

    try:
        return _hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True
