"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.security.rate_limit import LoginRateLimiter
from app.services.auth import (
    InvalidRefreshToken,
    RefreshTokenReuse,
    authenticate,
    issue_token_pair,
    normalize_email,
    record_audit,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
limiter = LoginRateLimiter(
    max_attempts=_settings.login_max_attempts,
    window_seconds=_settings.login_window_seconds,
)


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    host = request.client.host if request.client else None
    return host, request.headers.get("user-agent")


def _rate_key(host: str | None, email: str) -> str:
    return f"{host or 'unknown'}:{normalize_email(email)}"


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    host, user_agent = _client_meta(request)
    key = _rate_key(host, payload.email)

    if limiter.is_limited(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; try again later",
            headers={"Retry-After": str(_settings.login_window_seconds)},
        )

    user = authenticate(db, payload.email, payload.password)
    if user is None:
        limiter.record_failure(key)
        record_audit(
            db,
            action="LOGIN_FAILED",
            entity_type="user",
            detail={"email": normalize_email(payload.email)},
            ip_address=host,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    limiter.reset(key)
    record_audit(
        db,
        action="LOGIN",
        entity_type="user",
        user_id=user.id,
        entity_id=str(user.id),
        ip_address=host,
    )
    return issue_token_pair(
        db,
        user,
        user_agent=user_agent,
        ip_address=host,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    host, user_agent = _client_meta(request)
    try:
        return rotate_refresh_token(
            db,
            payload.refresh_token,
            user_agent=user_agent,
            ip_address=host,
        )
    except (InvalidRefreshToken, RefreshTokenReuse):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    host, _ = _client_meta(request)
    revoke_refresh_token(db, payload.refresh_token, ip_address=host)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
