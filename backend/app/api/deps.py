"""Shared FastAPI dependencies: authentication and ownership checks."""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Device, User
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized()

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(str(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _unauthorized("Invalid or expired token") from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("User is inactive or missing")
    return user


def require_roles(*roles: str):
    """Dependency factory for role-gated endpoints."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user

    return dependency


def owned_device_query(user: User):
    """Base query filtered to the caller's devices (admins see all)."""

    statement = select(Device).options(selectinload(Device.channels))
    if user.role != "admin":
        statement = statement.where(Device.owner_id == user.id)
    return statement


def get_device_for_user(db: Session, user: User, device_id: str) -> Device:
    """Return a device or raise 404.

    404 is deliberate for another user's device: it does not confirm that the
    device exists (docs/database_schema.md §5).
    """

    statement = owned_device_query(user).where(Device.device_id == device_id)
    device = db.scalar(statement)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    return device
