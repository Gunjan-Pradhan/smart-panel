"""Tests for Workstream 3: Safe Limits Policy, Limit Proposals, Clamping, and Audit Logging.

Verifies:
1. AI proposes safe limits during fingerprint extraction upon learning completion (limits_status = 'PROPOSED').
2. Limits remain inactive until explicit operator confirmation.
3. Operator confirmation endpoint clamps to hard caps (e.g. 25A on CH2 clamped to 10A, 20A on CH1 clamped to 16A).
4. Audit log records operator confirmation, requested limits, clamped limits, clamped flag, and operator ID.
5. Operator acceptance of proposed limits (empty payload).
6. Operator rejection of proposed limits (limits_status = 'REJECTED') with audit record.
7. Strict tenant isolation (Rule 6: 404 on other user's profile access).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.load_profile import LoadProfile
from app.models.user import User
from app.security import hash_password
from app.services.fingerprint import ReadingSample
from app.services.learning_manager import LearningSessionManager
from app.services.safe_limits import (
    HARD_CAPS_CH1,
    HARD_CAPS_CH2,
    confirm_profile_limits,
    get_channel_hard_caps,
    reject_profile_limits,
)

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


def auth_header(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": PASSWORD},
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
def users(db_session):
    alice = add_user(db_session, "alice@example.com")
    bob = add_user(db_session, "bob@example.com")
    db_session.commit()
    return {"alice": alice, "bob": bob}


def test_hard_caps_definition():
    """Verify channel hard caps match hardware protection specifications."""
    ch1 = get_channel_hard_caps(1)
    assert ch1.max_current_a == Decimal("16.000")
    assert ch1.max_power_w == Decimal("3680.00")
    assert ch1.min_voltage_v == Decimal("180.00")
    assert ch1.max_voltage_v == Decimal("265.00")
    assert ch1.max_inrush_blanking_ms == 3000

    ch2 = get_channel_hard_caps(2)
    assert ch2.max_current_a == Decimal("10.000")
    assert ch2.max_power_w == Decimal("2300.00")
    assert ch2.min_voltage_v == Decimal("180.00")
    assert ch2.max_voltage_v == Decimal("265.00")
    assert ch2.max_inrush_blanking_ms == 3000


def test_proposed_limits_created_on_learning_finalization(db_session, users):
    """When a learning session finishes with steady data, AI proposes limits but leaves them unconfirmed."""
    alice = users["alice"]
    manager = LearningSessionManager(db_session)
    session = manager.start_session(channel=2, is_simulated=True)

    # Steady 100W bulb: 230V, ~0.435A
    samples = [
        ReadingSample(
            voltage_v=230.0,
            current_a=0.435,
            active_power_w=100.05,
            power_factor=0.999,
            frequency_hz=50.0,
            timestamp_s=1000 + i,
        )
        for i in range(25)
    ]

    session, profile = manager.process_and_finalize_session(
        session.id,
        samples,
        profile_owner=alice,
        profile_name="Living Room 100W Bulb",
        min_readings=15,
    )

    assert session.status == "ready"
    assert profile is not None
    # Verify AI proposed limits are 125% of steady state
    assert profile.limits_status == "PROPOSED"
    assert profile.proposed_current_limit_a == Decimal("0.544")  # 0.435 * 1.25 = 0.54375 -> round 0.544
    assert profile.proposed_power_limit_w == Decimal("125.06")   # 100.05 * 1.25 = 125.0625 -> round 125.06
    assert profile.proposed_voltage_min_v == Decimal("180.00")
    assert profile.proposed_voltage_max_v == Decimal("260.00")
    assert profile.proposed_inrush_blanking_ms == 50

    # Confirmed limits MUST remain inactive (None) until operator acts
    assert profile.confirmed_current_limit_a is None
    assert profile.confirmed_power_limit_w is None
    assert profile.confirmed_voltage_min_v is None
    assert profile.confirmed_voltage_max_v is None
    assert profile.confirmed_inrush_blanking_ms is None
    assert profile.limits_confirmed_by is None
    assert profile.limits_confirmed_at is None
    assert profile.user_confirmed is False


def test_operator_confirms_proposed_limits_with_empty_payload(client, db_session, users):
    """Operator accepts the AI-proposed limits without changes."""
    alice = users["alice"]
    manager = LearningSessionManager(db_session)
    session = manager.start_session(channel=1, is_simulated=True)

    # 1.5 kW motor: 230V, 6.52A
    samples = [
        ReadingSample(
            voltage_v=230.0,
            current_a=6.52,
            active_power_w=1500.0,
            power_factor=0.88,
            frequency_hz=50.0,
            timestamp_s=1000 + i,
        )
        for i in range(20)
    ]
    _, profile = manager.process_and_finalize_session(
        session.id,
        samples,
        profile_owner=alice,
        profile_name="Workshop Compressor",
        min_readings=15,
    )

    headers = auth_header(client, alice.email)
    resp = client.post(
        f"/profiles/{profile.id}/confirm_limits",
        json={},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["limits_status"] == "CONFIRMED"
    assert data["user_confirmed"] is True
    assert Decimal(str(data["confirmed_current_limit_a"])) == profile.proposed_current_limit_a
    assert Decimal(str(data["confirmed_power_limit_w"])) == profile.proposed_power_limit_w
    assert Decimal(str(data["confirmed_voltage_min_v"])) == Decimal("180.00")
    assert Decimal(str(data["confirmed_voltage_max_v"])) == Decimal("260.00")
    assert data["confirmed_inrush_blanking_ms"] == 2000
    assert data["limits_confirmed_by"] == str(alice.id)
    assert data["limits_confirmed_at"] is not None

    # Verify audit log record
    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "load_profile",
            AuditLog.entity_id == str(profile.id),
            AuditLog.action == "CONFIRM_LIMITS",
        )
    ).scalar_one()
    assert audit.user_id == alice.id
    assert audit.detail["clamped"] is False
    assert audit.detail["confirmed"]["current_limit_a"] == float(profile.proposed_current_limit_a)


def test_operator_confirm_clamps_to_hardware_hard_caps(client, db_session, users):
    """Even if an operator requests dangerous limits, hardware hard caps strictly clamp them."""
    alice = users["alice"]
    # Create profile on Channel 2 (Hard cap: 10.0 A, 2300.0 W, 180-265 V, 3000 ms)
    profile = LoadProfile(
        owner_id=alice.id,
        display_name="Overloaded Heaters",
        channel_last_seen=2,
        nominal_power_w=Decimal("2000.0"),
        nominal_current_a=Decimal("8.7"),
        proposed_current_limit_a=Decimal("10.0"),
        proposed_power_limit_w=Decimal("2300.0"),
        proposed_voltage_min_v=Decimal("180.0"),
        proposed_voltage_max_v=Decimal("260.0"),
        proposed_inrush_blanking_ms=100,
        limits_status="PROPOSED",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    # Request dangerous values exceeding SSR-40DA / Channel 2 capabilities: 25.0 A, 5000 W, 150 V, 300 V, 5000 ms
    headers = auth_header(client, alice.email)
    resp = client.post(
        f"/profiles/{profile.id}/confirm_limits",
        json={
            "current_limit_a": 25.0,
            "power_limit_w": 5000.0,
            "voltage_min_v": 150.0,
            "voltage_max_v": 300.0,
            "inrush_blanking_ms": 5000,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Verify values were clamped to Channel 2 Hard Caps!
    assert Decimal(str(data["confirmed_current_limit_a"])) == Decimal("10.000")
    assert Decimal(str(data["confirmed_power_limit_w"])) == Decimal("2300.00")
    assert Decimal(str(data["confirmed_voltage_min_v"])) == Decimal("180.00")
    assert Decimal(str(data["confirmed_voltage_max_v"])) == Decimal("265.00")
    assert data["confirmed_inrush_blanking_ms"] == 3000
    assert data["limits_status"] == "CONFIRMED"

    # Verify audit log flagged clamped = True
    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "load_profile",
            AuditLog.entity_id == str(profile.id),
            AuditLog.action == "CONFIRM_LIMITS",
        )
    ).scalar_one()
    assert audit.detail["clamped"] is True
    assert audit.detail["requested"]["current_limit_a"] == 25.0
    assert audit.detail["confirmed"]["current_limit_a"] == 10.0


def test_operator_rejects_proposed_limits(client, db_session, users):
    """Operator can explicitly reject AI proposed limits."""
    alice = users["alice"]
    profile = LoadProfile(
        owner_id=alice.id,
        display_name="Untrusted Appliance",
        channel_last_seen=1,
        proposed_current_limit_a=Decimal("12.0"),
        proposed_power_limit_w=Decimal("2500.0"),
        proposed_voltage_min_v=Decimal("180.0"),
        proposed_voltage_max_v=Decimal("260.0"),
        proposed_inrush_blanking_ms=1500,
        limits_status="PROPOSED",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    headers = auth_header(client, alice.email)
    resp = client.post(
        f"/profiles/{profile.id}/reject_limits",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["limits_status"] == "REJECTED"
    assert data["confirmed_current_limit_a"] is None

    # Check audit log
    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "load_profile",
            AuditLog.entity_id == str(profile.id),
            AuditLog.action == "REJECT_LIMITS",
        )
    ).scalar_one()
    assert audit.user_id == alice.id


def test_tenant_isolation_foreign_user_gets_404(client, db_session, users):
    """A user attempting to confirm limits on another user's profile gets 404, never 403 (Rule 6)."""
    alice = users["alice"]
    bob = users["bob"]

    profile = LoadProfile(
        owner_id=alice.id,
        display_name="Alice Secret Machine",
        proposed_current_limit_a=Decimal("5.0"),
        proposed_power_limit_w=Decimal("1000.0"),
        proposed_voltage_min_v=Decimal("180.0"),
        proposed_voltage_max_v=Decimal("260.0"),
        proposed_inrush_blanking_ms=500,
        limits_status="PROPOSED",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    bob_headers = auth_header(client, bob.email)

    # Bob tries to confirm Alice's profile
    resp_confirm = client.post(
        f"/profiles/{profile.id}/confirm_limits",
        json={},
        headers=bob_headers,
    )
    assert resp_confirm.status_code == 404
    assert resp_confirm.json()["detail"] == "Profile not found"

    # Bob tries to reject Alice's profile
    resp_reject = client.post(
        f"/profiles/{profile.id}/reject_limits",
        headers=bob_headers,
    )
    assert resp_reject.status_code == 404
    assert resp_reject.json()["detail"] == "Profile not found"


def test_unauthenticated_request_returns_401(client, db_session, users):
    """Unauthenticated requests must be rejected with 401."""
    alice = users["alice"]
    profile = LoadProfile(
        owner_id=alice.id,
        display_name="Alice Machine",
        limits_status="PROPOSED",
    )
    db_session.add(profile)
    db_session.commit()

    resp = client.post(f"/profiles/{profile.id}/confirm_limits", json={})
    assert resp.status_code == 401
