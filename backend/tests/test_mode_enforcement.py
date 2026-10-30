"""Tests for Runtime Mode Enforcement Engine and REST API.

Covers:
- Always-On baseline relay cutoff guard and force override
- Motor Protection mode with DOL inrush filter vs sustained stall alert
- Household Lighting Eco mode with curfew tracking
- REST API: mode status, telemetry enforcement, command validation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models.channel import Channel
from app.models.device import Device
from app.models.event import Event
from app.models.load_profile import LoadModeSelection, LoadProfile
from app.models.user import User
from app.security import hash_password
from app.services.fingerprint import ReadingSample
from app.services.mode_enforcer import ModeEnforcer

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


def add_user(db_session, email: str = "operator@example.com") -> User:
    user = User(
        email=email,
        password_hash=PASSWORD_HASH,
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def add_device(db_session, owner: User) -> Device:
    dev = Device(
        device_id="PANEL-0001",
        name="Lab Test Panel",
        owner_id=owner.id,
    )
    db_session.add(dev)
    db_session.flush()

    ch1 = Channel(device_pk=dev.id, ch=1, name="Motor Channel")
    ch2 = Channel(device_pk=dev.id, ch=2, name="Bulb Channel")
    db_session.add(ch1)
    db_session.add(ch2)
    db_session.flush()
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


def auth_header(client: TestClient, email: str = "operator@example.com") -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_always_on_command_validation(db_session):
    user = add_user(db_session)
    enforcer = ModeEnforcer(db_session)

    # Setup profile with always_on mode enabled on Channel 1
    profile = LoadProfile(
        owner_id=user.id,
        display_name="Critical Baseline Server",
        channel_last_seen=1,
        nominal_power_w=12.0,
        nominal_current_a=0.06,
        user_confirmed=True,
    )
    db_session.add(profile)
    db_session.flush()

    mode = LoadModeSelection(
        profile_id=profile.id,
        mode_name="always_on",
        enabled=True,
        source="manual",
        selected_by=user.id,
    )
    db_session.add(mode)
    db_session.commit()

    # 1. ON command is always permitted
    allowed_on, reason_on, modes_on = enforcer.validate_command(1, user.id, "ON")
    assert allowed_on is True
    assert "always_on" in modes_on

    # 2. OFF command without force is rejected
    allowed_off, reason_off, _ = enforcer.validate_command(1, user.id, "OFF", force=False)
    assert allowed_off is False
    assert "Always-On baseline mode" in reason_off

    # 3. OFF command with force=True is permitted
    allowed_force, reason_force, _ = enforcer.validate_command(1, user.id, "OFF", force=True)
    assert allowed_force is True
    assert "force override" in reason_force


def test_motor_protection_stall_and_inrush(db_session):
    user = add_user(db_session, "engineer@example.com")
    device = add_device(db_session, user)
    enforcer = ModeEnforcer(db_session)

    # Setup profile with protection mode on Channel 1
    profile = LoadProfile(
        owner_id=user.id,
        display_name="Lab Induction Motor 125W",
        channel_last_seen=1,
        nominal_power_w=125.0,
        nominal_current_a=0.82,
        user_confirmed=True,
    )
    db_session.add(profile)
    db_session.flush()

    mode = LoadModeSelection(
        profile_id=profile.id,
        mode_name="protection",
        enabled=True,
        source="ai_suggestion",
        selected_by=user.id,
    )
    db_session.add(mode)
    db_session.commit()

    # 1. Normal running current (0.82A)
    sample_normal = ReadingSample(
        voltage_v=230.0,
        current_a=0.82,
        active_power_w=125.0,
        power_factor=0.66,
        frequency_hz=50.0,
    )
    res_nom = enforcer.evaluate_sample(
        1, user.id, sample_normal, is_startup_window=False, device_pk=device.id
    )
    assert res_nom.status == "normal"
    assert res_nom.event_logged is False

    # 2. Inrush during direct-on-line startup (3.0A, stall threshold = 1.5 * 0.82 = 1.23A)
    sample_high = ReadingSample(
        voltage_v=228.0,
        current_a=3.00,
        active_power_w=400.0,
        power_factor=0.60,
        frequency_hz=50.0,
    )
    res_inrush = enforcer.evaluate_sample(
        1, user.id, sample_high, is_startup_window=True, device_pk=device.id
    )
    assert res_inrush.status == "inrush_transient"
    assert res_inrush.severity == "info"
    assert res_inrush.event_logged is False

    # 3. Sustained locked-rotor stall during steady-state (3.0A, is_startup_window=False)
    res_stall = enforcer.evaluate_sample(
        1, user.id, sample_high, is_startup_window=False, device_pk=device.id
    )
    assert res_stall.status == "alert"
    assert res_stall.severity == "critical"
    assert res_stall.event_logged is True
    assert "stall threshold" in res_stall.advisories[0]


def test_eco_mode_curfew_tracking(db_session):
    user = add_user(db_session, "homeowner@example.com")
    device = add_device(db_session, user)
    enforcer = ModeEnforcer(db_session)

    profile = LoadProfile(
        owner_id=user.id,
        display_name="Living Room Chandelier",
        channel_last_seen=2,
        nominal_power_w=200.0,
        nominal_current_a=0.87,
        user_confirmed=True,
    )
    db_session.add(profile)
    db_session.flush()

    mode = LoadModeSelection(
        profile_id=profile.id,
        mode_name="eco",
        enabled=True,
        source="ai_suggestion",
        selected_by=user.id,
    )
    db_session.add(mode)
    db_session.commit()

    sample_on = ReadingSample(
        voltage_v=230.0,
        current_a=0.87,
        active_power_w=200.0,
        power_factor=0.99,
        frequency_hz=50.0,
    )

    # 1. Running during daytime (14:00) -> Normal
    res_day = enforcer.evaluate_sample(
        2, user.id, sample_on, current_hour=14, device_pk=device.id
    )
    assert res_day.status == "normal"
    assert res_day.event_logged is False

    # 2. Running during curfew hours (02:00) -> Curfew advisory
    res_night = enforcer.evaluate_sample(
        2, user.id, sample_on, current_hour=2, device_pk=device.id
    )
    assert res_night.status == "advisory"
    assert res_night.severity == "info"
    assert res_night.event_logged is True
    assert "curfew hours" in res_night.advisories[0]


def test_enforcement_api_workflow(client, db_session):
    user = add_user(db_session, "api_user@example.com")
    device = add_device(db_session, user)

    # Create profile with always_on and protection
    prof = LoadProfile(
        owner_id=user.id,
        display_name="Protected Channel 1 Load",
        channel_last_seen=1,
        nominal_power_w=125.0,
        nominal_current_a=0.82,
        user_confirmed=True,
    )
    db_session.add(prof)
    db_session.flush()

    m1 = LoadModeSelection(
        profile_id=prof.id,
        mode_name="always_on",
        enabled=True,
        source="manual",
        selected_by=user.id,
    )
    m2 = LoadModeSelection(
        profile_id=prof.id,
        mode_name="protection",
        enabled=True,
        source="ai_suggestion",
        selected_by=user.id,
    )
    db_session.add(m1)
    db_session.add(m2)
    db_session.commit()

    headers = auth_header(client, user.email)

    # 1. GET /channels/1/mode/status
    st_res = client.get("/channels/1/mode/status", headers=headers)
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert st_data["channel"] == 1
    assert st_data["is_always_on"] is True
    assert st_data["is_protection_active"] is True
    assert "always_on" in st_data["enabled_modes"]
    assert "protection" in st_data["enabled_modes"]

    # 2. POST /channels/1/commands/validate -> OFF without force rejected
    v_reject = client.post(
        "/channels/1/commands/validate",
        json={"action": "OFF", "force": False},
        headers=headers,
    )
    assert v_reject.status_code == 200
    assert v_reject.json()["allowed"] is False

    # 3. POST /channels/1/commands/validate -> OFF with force allowed
    v_force = client.post(
        "/channels/1/commands/validate",
        json={"action": "OFF", "force": True},
        headers=headers,
    )
    assert v_force.status_code == 200
    assert v_force.json()["allowed"] is True

    # 4. POST /channels/1/enforce -> Evaluates telemetry
    enf_res = client.post(
        "/channels/1/enforce",
        json={
            "sample": {
                "voltage_v": 230.0,
                "current_a": 0.82,
                "active_power_w": 125.0,
                "power_factor": 0.66,
                "frequency_hz": 50.0,
            },
            "is_startup_window": False,
        },
        headers=headers,
    )
    assert enf_res.status_code == 200
    assert enf_res.json()["channel"] == 1

    # 5. Channel validation: Channel 3 rejected
    inv_res = client.get("/channels/3/mode/status", headers=headers)
    assert inv_res.status_code == 422

