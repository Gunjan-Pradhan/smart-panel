"""Tests for Workstream 7: Local Schedules & Timers.

Verifies:
1.  Create schedule happy path → 201 with correct response body.
2.  days_of_week bitmask validation (must be 1-127).
3.  on_time == off_time rejected with 422.
4.  Viewer member cannot create a schedule (403).
5.  List schedules returns only the current user's schedules.
6.  Get single schedule by ID → 200.
7.  Get another user's schedule → 404 (tenant isolation, Rule 6).
8.  Update schedule (PATCH enabled=False) → 200.
9.  Delete schedule → 204, then 404.
10. MQTT publish is attempted on create (stubbed).
"""

from __future__ import annotations

import uuid
from datetime import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models import Channel, Device, DeviceMember, Schedule, User
from app.security import hash_password

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def auth_header(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


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
    owner = add_user(db_session, "sched_owner@example.com")
    other = add_user(db_session, "sched_other@example.com")
    viewer = add_user(db_session, "sched_viewer@example.com")

    device = Device(
        device_id="PANEL-0070",
        name="Schedule Test Panel",
        owner_id=owner.id,
        online=True,
    )
    db_session.add(device)
    db_session.flush()

    # Give viewer a 'viewer' membership on the device
    membership = DeviceMember(
        device_id=device.id,
        user_id=viewer.id,
        role="viewer",
    )
    db_session.add(membership)

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
        "other": other,
        "viewer": viewer,
        "device": device,
    }


# Standard schedule body used by most tests
SCHED_BODY = {
    "device_id": "PANEL-0070",
    "ch": 1,
    "name": "Morning Motor Run",
    "days_of_week": 31,  # Mon-Fri  (1+2+4+8+16)
    "on_time": "06:00:00",
    "off_time": "08:00:00",
    "timezone": "Asia/Kolkata",
    "enabled": True,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_schedule_happy_path(client, setup_data):
    """Owner can create a schedule; response contains correct fields."""
    owner = setup_data["owner"]
    hdr = auth_header(client, owner.email)

    # Stub MQTT so the test does not need a broker
    with patch("app.api.schedules._publish_schedule_sync"):
        resp = client.post("/schedules", json=SCHED_BODY, headers=hdr)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Morning Motor Run"
    assert data["ch"] == 1
    assert data["days_of_week"] == 31
    assert data["on_time"] == "06:00:00"
    assert data["off_time"] == "08:00:00"
    assert data["timezone"] == "Asia/Kolkata"
    assert data["enabled"] is True
    assert data["device_id"] == "PANEL-0070"
    # Must return a valid UUID
    uuid.UUID(data["id"])


def test_days_of_week_out_of_range_rejected(client, setup_data):
    """days_of_week=0 and days_of_week=128 must both be rejected (422)."""
    owner = setup_data["owner"]
    hdr = auth_header(client, owner.email)

    for bad_value in (0, 128, -1):
        body = {**SCHED_BODY, "days_of_week": bad_value}
        resp = client.post("/schedules", json=body, headers=hdr)
        assert resp.status_code == 422, f"Expected 422 for days_of_week={bad_value}"


def test_same_on_off_time_rejected(client, setup_data):
    """on_time == off_time must be rejected with 422."""
    owner = setup_data["owner"]
    hdr = auth_header(client, owner.email)

    body = {**SCHED_BODY, "on_time": "07:00:00", "off_time": "07:00:00"}
    with patch("app.api.schedules._publish_schedule_sync"):
        resp = client.post("/schedules", json=body, headers=hdr)
    assert resp.status_code == 422
    assert "on_time" in resp.json()["detail"] or "different" in resp.json()["detail"]


def test_viewer_cannot_create_schedule(client, setup_data):
    """A 'viewer' member cannot create schedules (403)."""
    viewer = setup_data["viewer"]
    hdr = auth_header(client, viewer.email)

    with patch("app.api.schedules._publish_schedule_sync"):
        resp = client.post("/schedules", json=SCHED_BODY, headers=hdr)
    assert resp.status_code == 403
    assert "Viewers" in resp.json()["detail"]


def test_list_schedules_only_own(client, db_session, setup_data):
    """List endpoint returns only the authenticated user's schedules."""
    owner = setup_data["owner"]
    other = setup_data["other"]
    device = setup_data["device"]

    # Create a second device for 'other' user so they can own a schedule
    device2 = Device(
        device_id="PANEL-0071",
        name="Other Panel",
        owner_id=other.id,
        online=False,
    )
    db_session.add(device2)
    db_session.flush()

    # Insert one schedule for owner, one for other directly in DB
    s1 = Schedule(
        owner_id=owner.id,
        device_pk=device.id,
        ch=1,
        name="Owner's Schedule",
        days_of_week=1,
        on_time=time(6, 0),
        off_time=time(8, 0),
        timezone="Asia/Kolkata",
        enabled=True,
    )
    s2 = Schedule(
        owner_id=other.id,
        device_pk=device2.id,
        ch=2,
        name="Other's Schedule",
        days_of_week=2,
        on_time=time(9, 0),
        off_time=time(11, 0),
        timezone="Asia/Kolkata",
        enabled=True,
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    owner_hdr = auth_header(client, owner.email)
    resp = client.get("/schedules", headers=owner_hdr)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Owner's Schedule"


def test_get_single_schedule(client, db_session, setup_data):
    """GET /schedules/{id} returns the schedule correctly."""
    owner = setup_data["owner"]
    device = setup_data["device"]

    sched = Schedule(
        owner_id=owner.id,
        device_pk=device.id,
        ch=2,
        name="Night Shutdown",
        days_of_week=127,  # Every day
        on_time=time(22, 0),
        off_time=time(23, 59),
        timezone="UTC",
        enabled=False,
    )
    db_session.add(sched)
    db_session.commit()

    hdr = auth_header(client, owner.email)
    resp = client.get(f"/schedules/{sched.id}", headers=hdr)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Night Shutdown"
    assert resp.json()["enabled"] is False


def test_get_other_user_schedule_returns_404(client, db_session, setup_data):
    """Tenant isolation: fetching another user's schedule returns 404, not 403."""
    owner = setup_data["owner"]
    other = setup_data["other"]
    device = setup_data["device"]

    sched = Schedule(
        owner_id=owner.id,
        device_pk=device.id,
        ch=1,
        name="Private Schedule",
        days_of_week=4,
        on_time=time(10, 0),
        off_time=time(12, 0),
        timezone="UTC",
        enabled=True,
    )
    db_session.add(sched)
    db_session.commit()

    other_hdr = auth_header(client, other.email)
    resp = client.get(f"/schedules/{sched.id}", headers=other_hdr)
    assert resp.status_code == 404  # Rule 6: 404, never 403


def test_update_schedule_patch_enabled(client, db_session, setup_data):
    """PATCH /schedules/{id} with enabled=False disables the schedule."""
    owner = setup_data["owner"]
    device = setup_data["device"]

    sched = Schedule(
        owner_id=owner.id,
        device_pk=device.id,
        ch=1,
        name="Patchable Schedule",
        days_of_week=16,  # Friday only
        on_time=time(7, 0),
        off_time=time(9, 0),
        timezone="Asia/Kolkata",
        enabled=True,
    )
    db_session.add(sched)
    db_session.commit()

    hdr = auth_header(client, owner.email)
    with patch("app.api.schedules._publish_schedule_sync"):
        resp = client.patch(
            f"/schedules/{sched.id}",
            json={"enabled": False, "name": "Patched Name"},
            headers=hdr,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["name"] == "Patched Name"
    # Other fields unchanged
    assert data["days_of_week"] == 16


def test_delete_schedule(client, db_session, setup_data):
    """DELETE /schedules/{id} returns 204, subsequent GET returns 404."""
    owner = setup_data["owner"]
    device = setup_data["device"]

    sched = Schedule(
        owner_id=owner.id,
        device_pk=device.id,
        ch=1,
        name="Deletable Schedule",
        days_of_week=64,  # Sunday only
        on_time=time(5, 0),
        off_time=time(6, 0),
        timezone="UTC",
        enabled=True,
    )
    db_session.add(sched)
    db_session.commit()

    hdr = auth_header(client, owner.email)
    with patch("app.api.schedules._publish_schedule_sync"):
        del_resp = client.delete(f"/schedules/{sched.id}", headers=hdr)
    assert del_resp.status_code == 204

    get_resp = client.get(f"/schedules/{sched.id}", headers=hdr)
    assert get_resp.status_code == 404


def test_mqtt_publish_called_on_create(client, db_session, setup_data):
    """MQTT publish helper is invoked exactly once when a schedule is created."""
    owner = setup_data["owner"]
    hdr = auth_header(client, owner.email)

    with patch("app.api.schedules._publish_schedule_sync") as mock_publish:
        resp = client.post("/schedules", json=SCHED_BODY, headers=hdr)
    assert resp.status_code == 201
    mock_publish.assert_called_once()
