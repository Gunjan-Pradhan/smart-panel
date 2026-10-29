"""Authentication service: login, refresh-token rotation and audit entries.

Design reference: docs/database_schema.md §6.

Rules enforced here:
- a disabled user cannot log in or refresh;
- refresh tokens are single-use and rotated;
- reuse of a rotated token revokes the whole family and is audited;
- passwords and raw tokens are never written to the audit log.
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, RefreshToken, User
from app.schemas.auth import TokenResponse
from app.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)


class AuthError(Exception):
    """Base class for expected authentication failures."""


class InvalidCredentials(AuthError):
    pass


class InvalidRefreshToken(AuthError):
    pass


class RefreshTokenReuse(AuthError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def clean_ip(value: str | None) -> str | None:
    """Return a valid IP string or None.

    Test clients and some proxies use hostnames such as "testclient"; casting
    those into an ``inet`` column would raise a database error.
    """

    if not value:
        return None
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return None
    return value


def record_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    user_id: uuid.UUID | None = None,
    entity_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            ip_address=clean_ip(ip_address),
        )
    )


def authenticate(
    session: Session,
    email: str,
    password: str,
) -> User | None:
    """Return the user on success, or None for any failure (no detail leak)."""

    normalized = normalize_email(email)
    user = session.scalar(
        select(User).where(func.lower(User.email) == normalized)
    )
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    return user


def _new_token_row(
    user: User,
    *,
    family_id: uuid.UUID,
    issued_at: datetime,
    replaced_by_id: uuid.UUID | None,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[RefreshToken, str]:
    raw = new_refresh_token()
    settings = get_settings()
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw),
        family_id=family_id,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=settings.refresh_token_days),
        replaced_by_id=replaced_by_id,
        user_agent=(user_agent[:512] if user_agent else None),
        ip_address=clean_ip(ip_address),
    )
    return row, raw


def _token_response(user: User, raw_refresh: str) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_minutes * 60,
    )


def issue_token_pair(
    session: Session,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    now = _now()
    row, raw = _new_token_row(
        user,
        family_id=uuid.uuid4(),
        issued_at=now,
        replaced_by_id=None,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(row)
    session.commit()
    return _token_response(user, raw)


def rotate_refresh_token(
    session: Session,
    raw_token: str,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    token_hash = hash_refresh_token(raw_token)
    token = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if token is None:
        raise InvalidRefreshToken("unknown refresh token")

    now = _now()

    if token.revoked_at is not None:
        # Reuse detection: revoke every token in the family, including the
        # successor that the legitimate client may already hold.
        result = session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == token.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        # Only audit the first detection: later replays of an already-revoked
        # family must not flood the audit log.
        if result.rowcount:
            record_audit(
                session,
                action="REFRESH_TOKEN_REUSE",
                entity_type="refresh_token",
                user_id=token.user_id,
                entity_id=str(token.id),
                detail={"family_id": str(token.family_id)},
                ip_address=ip_address,
            )
        session.commit()
        raise RefreshTokenReuse("refresh token reuse detected")

    if token.expires_at <= now:
        raise InvalidRefreshToken("refresh token expired")

    user = session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshToken("user is not active")

    token.revoked_at = now
    row, raw = _new_token_row(
        user,
        family_id=token.family_id,
        issued_at=now,
        replaced_by_id=token.id,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(row)
    record_audit(
        session,
        action="TOKEN_REFRESH",
        entity_type="refresh_token",
        user_id=user.id,
        entity_id=str(token.id),
        detail={"family_id": str(token.family_id)},
        ip_address=ip_address,
    )
    session.commit()
    return _token_response(user, raw)


def revoke_refresh_token(
    session: Session,
    raw_token: str,
    *,
    ip_address: str | None = None,
) -> bool:
    token = session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw_token)
        )
    )
    if token is None:
        return False

    if token.revoked_at is None:
        token.revoked_at = _now()
        record_audit(
            session,
            action="LOGOUT",
            entity_type="refresh_token",
            user_id=token.user_id,
            entity_id=str(token.id),
            detail={"family_id": str(token.family_id)},
            ip_address=ip_address,
        )
        session.commit()
    return True
