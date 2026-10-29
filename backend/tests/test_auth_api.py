"""Authentication and ownership tests.

These tests run against the real PostgreSQL test database through FastAPI's
TestClient. They prove that:

- a valid login returns a short-lived access token and a refresh token;
- wrong passwords are rejected and audited;
- refresh tokens rotate and reuse revokes the whole family;
- a user cannot read another user's device or channels (404, not 403);
- an admin can read every device.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Channel, Device, User
from app.security import hash_password

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


def add_user(
    db_session,
    email: str,
    *,
    role: str = "viewer",
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=PASSWORD_HASH,
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def add_device(db_session, owner: User, device_id: str, *, name: str) -> Device:
    device = Device(device_id=device_id, name=name, owner_id=owner.id)
    db_session.add(device)
    db_session.flush()
    db_session.add(
        Channel(device_pk=device.id, ch=1, name="Motor"),
    )
    db_session.add(
        Channel(device_pk=device.id, ch=2, name="Bulb"),
    )
    db_session.flush()
    return device


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    limiter.clear()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.clear()


@pytest.fixture()
def accounts(db_session):
    owner = add_user(db_session, "owner@example.com", role="operator")
    other = add_user(db_session, "other@example.com", role="operator")
    admin = add_user(db_session, "admin@example.com", role="admin")
    add_device(db_session, owner, "PANEL-0001", name="Owner panel")
    add_device(db_session, other, "PANEL-0002", name="Other panel")
    db_session.commit()
    return owner, other, admin


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def auth_header(client: TestClient, email: str) -> dict[str, str]:
    response = login(client, email)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_returns_tokens_and_me_hides_password(client, accounts) -> None:
    response = login(client, "owner@example.com")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 15 * 60

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"
    assert "password" not in me.text


def test_wrong_password_is_rejected_and_audited(db_session, client, accounts) -> None:
    response = login(client, "owner@example.com", "wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"

    failures = db_session.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "LOGIN_FAILED")
    ).scalar()
    assert failures == 1


def test_unknown_email_gets_the_same_generic_error(client, accounts) -> None:
    response = login(client, "missing@example.com")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_refresh_rotates_and_reuse_revokes_the_family(
    db_session, client, accounts
) -> None:
    first = login(client, "owner@example.com").json()

    rotated = client.post(
        "/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]

    # Replaying the consumed token must fail and revoke the successor too.
    replay = client.post(
        "/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert replay.status_code == 401

    successor = client.post(
        "/auth/refresh",
        json={"refresh_token": second["refresh_token"]},
    )
    assert successor.status_code == 401

    reuse_events = db_session.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "REFRESH_TOKEN_REUSE")
    ).scalar()
    assert reuse_events == 1


def test_logout_revokes_the_refresh_token(client, accounts) -> None:
    tokens = login(client, "owner@example.com").json()

    response = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 204

    refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 401


def test_missing_or_invalid_access_token_is_rejected(client, accounts) -> None:
    assert client.get("/devices").status_code == 401
    assert (
        client.get(
            "/devices",
            headers={"Authorization": "Bearer not-a-jwt"},
        ).status_code
        == 401
    )


def test_user_cannot_read_another_users_device(client, accounts) -> None:
    headers = auth_header(client, "owner@example.com")

    own = client.get("/devices", headers=headers)
    assert own.status_code == 200
    assert [d["device_id"] for d in own.json()] == ["PANEL-0001"]

    foreign = client.get("/devices/PANEL-0002", headers=headers)
    assert foreign.status_code == 404

    foreign_channels = client.get(
        "/devices/PANEL-0002/channels", headers=headers
    )
    assert foreign_channels.status_code == 404


def test_admin_can_read_every_device(client, accounts) -> None:
    headers = auth_header(client, "admin@example.com")

    listing = client.get("/devices", headers=headers)
    assert listing.status_code == 200
    assert {d["device_id"] for d in listing.json()} == {
        "PANEL-0001",
        "PANEL-0002",
    }

    detail = client.get("/devices/PANEL-0002", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["channels"]) == 2


def test_deactivated_user_cannot_login_or_use_an_old_token(
    db_session, client, accounts
) -> None:
    owner, _, _ = accounts
    headers = auth_header(client, "owner@example.com")
    assert client.get("/auth/me", headers=headers).status_code == 200

    owner.is_active = False
    owner.updated_at = datetime.now(timezone.utc)
    db_session.commit()

    assert login(client, "owner@example.com").status_code == 401
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_login_is_rate_limited(client, accounts) -> None:
    for _ in range(5):
        assert login(client, "owner@example.com", "wrong").status_code == 401

    blocked = login(client, "owner@example.com", "wrong")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
