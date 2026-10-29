"""JWT access tokens and opaque refresh tokens.

Access tokens are stateless and short-lived. Refresh tokens are random,
stored only as SHA-256 hashes, and rotated on every use.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token.

    Raises ``jwt.InvalidTokenError`` for an invalid signature, expiry or a
    missing required claim.
    """

    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )


def new_refresh_token() -> str:
    """256 bits of randomness, URL-safe."""

    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex digest; the raw value is never stored."""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
