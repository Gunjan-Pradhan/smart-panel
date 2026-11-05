"""Tests for Workstream 4: Remote Control with Real Ack.

Verifies:
- Command dispatch through POST /devices/{device_id}/commands
- Status progression: PENDING -> SENT -> DONE / REJECTED
- Channel state synchronization on ack
- Command expiration and timeout marking
- Role enforcement: viewers get 403
- Tenant isolation: non-owners get 404 (Rule 6)
- Payload and channel validation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models import Channel, Command, Device, User
from app.security import hash_password
from app.services.command_service import check_command_timeouts

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


def create_user(db, email: str, role: str = "operator") -> User:
    user = User(
        email=email,
        password_hash=PASSWORD_HASH,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def create_device(db, owner: User, device_id: str = "PANEL-0001") -> Device:
    dev = Device(device_id=device_id, name="Test Panel", owner_id=owner.id)
    db.add(dev)
    db.flush()
    ch1 = Channel(device_pk=dev.id, ch=1, name="Channel 1", relay_commanded=False, state="OFF")
    ch2 = Channel(device_pk=dev.id, ch=2, name="Channel 2", relay_commanded=False, state="OFF")
    db.add_all([ch1, ch2])
    db.flush()
    return dev


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


def auth_header(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_command_happy_path_sent_and_ack_done(client, db_session) -> None:
    owner = create_user(db_session, "owner@example.com", role="operator")
    device = create_device(db_session, owner, "PANEL-0001")
    db_session.commit()

    headers = auth_header(client, owner.email)

    # 1. Issue command ON
    res = client.post(
        f"/devices/{device.device_id}/commands",
        json={
            "ch": 1,
            "action": "ON",
            "duration_seconds": 3600,
            "priority": "user",
            "source": "user",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["ch"] == 1
    assert data["action"] == "ON"
    assert data["status"] == "SENT"
    cmd_id = data["cmd_id"]

    # Verify database state
    cmd = db_session.scalar(select(Command).where(Command.cmd_id == uuid.UUID(cmd_id)))
    assert cmd is not None
    assert cmd.status == "SENT"
    assert cmd.acked_at is None

    # 2. Simulate firmware ack: DONE
    now_ts = datetime.now(timezone.utc).timestamp()
    ack_res = client.post(
        f"/devices/{device.device_id}/commands/ack",
        json={
            "cmd_id": cmd_id,
            "ch": 1,
            "result": "DONE",
            "reason": "OK",
            "relay": True,
            "state": "RUNNING",
            "ts": now_ts,
        },
        headers=headers,
    )
    assert ack_res.status_code == 200, ack_res.text
    ack_data = ack_res.json()
    assert ack_data["status"] == "DONE"
    assert ack_data["relay_after"] is True
    assert ack_data["state_after"] == "RUNNING"
    assert ack_data["executed_at"] is not None

    # 3. Verify channel state was updated
    ch1 = db_session.scalar(
        select(Channel).where(Channel.device_pk == device.id, Channel.ch == 1)
    )
    assert ch1.relay_commanded is True
    assert ch1.state == "RUNNING"


def test_command_refused_during_lockout(client, db_session) -> None:
    owner = create_user(db_session, "owner2@example.com", role="operator")
    device = create_device(db_session, owner, "PANEL-0002")
    db_session.commit()

    headers = auth_header(client, owner.email)

    res = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 2, "action": "ON"},
        headers=headers,
    )
    assert res.status_code == 201
    cmd_id = res.json()["cmd_id"]

    # Firmware reports REFUSED due to safety lockout
    ack_res = client.post(
        f"/devices/{device.device_id}/commands/ack",
        json={
            "cmd_id": cmd_id,
            "ch": 2,
            "result": "REFUSED",
            "reason": "COMMAND_REFUSED_LOCKOUT",
            "relay": False,
            "state": "LOCKOUT",
        },
        headers=headers,
    )
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["status"] == "REJECTED"
    assert ack_data["reason"] == "COMMAND_REFUSED_LOCKOUT"
    assert ack_data["relay_after"] is False
    assert ack_data["state_after"] == "LOCKOUT"


def test_command_timeout_worker(client, db_session) -> None:
    owner = create_user(db_session, "owner3@example.com", role="operator")
    device = create_device(db_session, owner, "PANEL-0003")
    db_session.commit()

    headers = auth_header(client, owner.email)

    res = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 1, "action": "OFF"},
        headers=headers,
    )
    assert res.status_code == 201
    cmd_id = uuid.UUID(res.json()["cmd_id"])

    # Simulate expired command by backdating issued_at and expires_at
    now = datetime.now(timezone.utc)
    cmd = db_session.get(Command, cmd_id)
    cmd.issued_at = now - timedelta(seconds=20)
    cmd.expires_at = now - timedelta(seconds=5)
    db_session.commit()

    # Run timeout sweeper
    timed_out_count = check_command_timeouts(db_session)
    assert timed_out_count >= 1

    db_session.refresh(cmd)
    assert cmd.status == "TIMED_OUT"
    assert cmd.reason == "TIMEOUT_NO_ACK"


def test_permission_viewer_cannot_command(client, db_session) -> None:
    viewer = create_user(db_session, "viewer@example.com", role="viewer")
    device = create_device(db_session, viewer, "PANEL-0004")
    db_session.commit()

    headers = auth_header(client, viewer.email)

    res = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 1, "action": "ON"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "Viewers cannot issue commands" in res.json()["detail"]


def test_tenant_isolation_other_user_device_returns_404(client, db_session) -> None:
    alice = create_user(db_session, "alice@example.com", role="operator")
    bob = create_user(db_session, "bob@example.com", role="operator")
    alice_device = create_device(db_session, alice, "PANEL-0007")
    db_session.commit()

    # Bob attempts to command Alice's device
    bob_headers = auth_header(client, bob.email)
    res = client.post(
        f"/devices/{alice_device.device_id}/commands",
        json={"ch": 1, "action": "ON"},
        headers=bob_headers,
    )
    # Must return 404, NEVER 403 (Rule 6)
    assert res.status_code == 404
    assert res.json()["detail"] == "Device not found"


def test_invalid_channel_and_action_payloads(client, db_session) -> None:
    owner = create_user(db_session, "owner5@example.com", role="operator")
    device = create_device(db_session, owner, "PANEL-0005")
    db_session.commit()

    headers = auth_header(client, owner.email)

    # Invalid channel 3
    res1 = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 3, "action": "ON"},
        headers=headers,
    )
    assert res1.status_code == 422

    # Invalid action TOGGLE
    res2 = client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 1, "action": "TOGGLE"},
        headers=headers,
    )
    assert res2.status_code == 422


def test_list_commands_endpoint(client, db_session) -> None:
    owner = create_user(db_session, "owner6@example.com", role="operator")
    device = create_device(db_session, owner, "PANEL-0006")
    db_session.commit()

    headers = auth_header(client, owner.email)

    client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 1, "action": "ON"},
        headers=headers,
    )
    client.post(
        f"/devices/{device.device_id}/commands",
        json={"ch": 2, "action": "OFF"},
        headers=headers,
    )

    list_res = client.get(
        f"/devices/{device.device_id}/commands",
        headers=headers,
    )
    assert list_res.status_code == 200
    cmds = list_res.json()
    assert len(cmds) == 2
    assert cmds[0]["ch"] in (1, 2)
    assert cmds[1]["ch"] in (1, 2)
