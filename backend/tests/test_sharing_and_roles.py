"""Tests for Workstream 6: Multi-User Accounts, Sharing & Roles.

Verifies:
1. User registration (POST /auth/register) with validation, duplicate detection, and audit logging.
2. Multi-user device sharing (POST /devices/{id}/members) with 'admin' and 'viewer' roles.
3. Role permission enforcement:
   - 'viewer' members can view device and channels, but cannot issue commands (403).
   - 'admin' members can issue commands (201).
   - 'viewer' members cannot share the device (403).
4. Revoking membership (DELETE /devices/{id}/members/{user_id}) restores strict isolation (404).
5. Audit logging for device sharing, unsharing, and registration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Channel, Device, DeviceMember, User
from app.security import hash_password

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


def add_user(db_session, email: str, role: str = "operator") -> User:
    user = User(
        email=email,
        password_hash=PASSWORD_HASH,
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def auth_header(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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
def setup_data(db_session):
    owner = add_user(db_session, "owner@example.com", role="operator")
    alice = add_user(db_session, "alice@example.com", role="operator")
    stranger = add_user(db_session, "stranger@example.com", role="operator")

    device = Device(
        device_id="PANEL-0060",
        name="Main Workshop Panel",
        owner_id=owner.id,
        online=True,
    )
    db_session.add(device)
    db_session.flush()

    ch1 = Channel(
        device_pk=device.id,
        ch=1,
        name="CH1 Motor",
        state="OFF",
        relay_commanded=False,
    )
    db_session.add(ch1)
    db_session.commit()

    return {
        "owner": owner,
        "alice": alice,
        "stranger": stranger,
        "device": device,
        "ch1": ch1,
    }


def test_user_registration_happy_path(client, db_session):
    """Registering a new user creates account, hashes password, logs audit, and returns tokens."""
    payload = {
        "email": "NewUser@Example.com",
        "password": "SecurePassword123!",
        "role": "operator",
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Verify user saved lowercase
    user = db_session.scalar(
        select(User).where(User.email == "newuser@example.com")
    )
    assert user is not None
    assert user.role == "operator"

    # Verify audit log
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "user",
            AuditLog.action == "REGISTER",
            AuditLog.entity_id == str(user.id),
        )
    )
    assert audit is not None
    assert audit.detail["email"] == "newuser@example.com"


def test_user_registration_duplicate_rejected(client, db_session):
    """Registering with an already existing email returns 409 Conflict."""
    add_user(db_session, "existing@example.com")
    db_session.commit()

    resp = client.post(
        "/auth/register",
        json={
            "email": "Existing@Example.com",
            "password": "Password123!",
            "role": "operator",
        },
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_user_registration_cannot_self_assign_admin(client):
    """Users cannot register themselves as admin role."""
    resp = client.post(
        "/auth/register",
        json={
            "email": "hacker@example.com",
            "password": "Password123!",
            "role": "admin",
        },
    )
    assert resp.status_code == 422  # Pydantic validation failure on pattern


def test_device_sharing_and_role_permissions(client, db_session, setup_data):
    """Comprehensive test of sharing, role permissions, and revocation."""
    owner = setup_data["owner"]
    alice = setup_data["alice"]
    stranger = setup_data["stranger"]
    device = setup_data["device"]

    owner_hdr = auth_header(client, owner.email)
    alice_hdr = auth_header(client, alice.email)
    stranger_hdr = auth_header(client, stranger.email)

    # 1. Before sharing: Alice cannot see the device (404 Rule 6)
    resp = client.get(f"/devices/{device.device_id}", headers=alice_hdr)
    assert resp.status_code == 404

    # 2. Owner shares device with Alice as 'viewer'
    share_resp = client.post(
        f"/devices/{device.device_id}/members",
        json={"email": alice.email, "role": "viewer"},
        headers=owner_hdr,
    )
    assert share_resp.status_code == 201, share_resp.text
    member_data = share_resp.json()
    assert member_data["email"] == alice.email
    assert member_data["role"] == "viewer"

    # Verify audit log
    audit_share = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "device",
            AuditLog.action == "DEVICE_SHARED",
            AuditLog.entity_id == device.device_id,
        )
    )
    assert audit_share is not None
    assert audit_share.detail["shared_with"] == alice.email
    assert audit_share.detail["role"] == "viewer"

    # 3. Alice can now view the device
    resp = client.get(f"/devices/{device.device_id}", headers=alice_hdr)
    assert resp.status_code == 200
    assert resp.json()["device_id"] == device.device_id

    # 4. As a 'viewer', Alice is FORBIDDEN from issuing commands (403)
    cmd_resp = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 1, "action": "ON"},
        headers=alice_hdr,
    )
    assert cmd_resp.status_code == 403
    assert "Viewers cannot issue commands" in cmd_resp.json()["detail"]

    # 5. Alice as 'viewer' cannot share the device with others
    viewer_share_resp = client.post(
        f"/devices/{device.device_id}/members",
        json={"email": stranger.email, "role": "viewer"},
        headers=alice_hdr,
    )
    assert viewer_share_resp.status_code == 403

    # 6. Owner upgrades Alice to 'admin'
    upgrade_resp = client.post(
        f"/devices/{device.device_id}/members",
        json={"email": alice.email, "role": "admin"},
        headers=owner_hdr,
    )
    assert upgrade_resp.status_code == 201
    assert upgrade_resp.json()["role"] == "admin"

    # 7. As an 'admin' member, Alice CAN now issue commands!
    cmd_resp2 = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 1, "action": "ON"},
        headers=alice_hdr,
    )
    assert cmd_resp2.status_code == 201
    assert cmd_resp2.json()["status"] == "SENT"

    # 8. List members check
    members_resp = client.get(f"/devices/{device.device_id}/members", headers=owner_hdr)
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["user_id"] == str(alice.id)
    assert members[0]["role"] == "admin"

    # 9. Owner revokes Alice's membership
    del_resp = client.delete(
        f"/devices/{device.device_id}/members/{alice.id}",
        headers=owner_hdr,
    )
    assert del_resp.status_code == 204

    # Verify audit log for unshare
    audit_unshare = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "device",
            AuditLog.action == "DEVICE_UNSHARED",
            AuditLog.entity_id == device.device_id,
        )
    )
    assert audit_unshare is not None

    # 10. After revocation, Alice gets 404 again (Rule 6: tenant isolation)
    resp_after = client.get(f"/devices/{device.device_id}", headers=alice_hdr)
    assert resp_after.status_code == 404


def test_cannot_share_with_self_or_nonexistent_user(client, setup_data):
    """Sharing with owner returns 400; sharing with unknown email returns 404."""
    owner = setup_data["owner"]
    device = setup_data["device"]
    owner_hdr = auth_header(client, owner.email)

    # Share with self (device owner)
    resp_self = client.post(
        f"/devices/{device.device_id}/members",
        json={"email": owner.email, "role": "viewer"},
        headers=owner_hdr,
    )
    assert resp_self.status_code == 400
    assert "already the owner" in resp_self.json()["detail"]

    # Share with nonexistent user
    resp_unknown = client.post(
        f"/devices/{device.device_id}/members",
        json={"email": "nobody@example.com", "role": "viewer"},
        headers=owner_hdr,
    )
    assert resp_unknown.status_code == 404
    assert "User not found" in resp_unknown.json()["detail"]

