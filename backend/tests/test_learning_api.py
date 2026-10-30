"""Tests for Learning Session Manager and Load Profile REST API.

Covers:
- Learning session start, status polling, and cancellation.
- Session finalization state machine (ready, unstable, insufficient_data).
- Load profile CRUD, rename, and user confirmation.
- Strict multi-tenant ownership isolation (404 on foreign profile access).
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
from app.models.load_profile import LearningSession, LoadProfile, ProfileFingerprint
from app.models.user import User
from app.security import hash_password
from app.services.fingerprint import ReadingSample
from app.services.learning_manager import LearningSessionManager

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
    return alice, bob


def auth_header(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_start_and_get_learning_status(client, users, db_session) -> None:
    alice, _ = users
    headers = auth_header(client, alice.email)

    # Initially no active session
    res = client.get("/channels/1/learning/status", headers=headers)
    assert res.status_code == 200
    assert res.json() is None

    # Start session on Channel 1
    res = client.post(
        "/channels/1/learning/start",
        json={"is_simulated": True},
        headers=headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["channel"] == 1
    assert body["status"] == "learning"
    assert body["is_simulated"] is True
    session_id = body["id"]

    # Now status returns active session
    res = client.get("/channels/1/learning/status", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == session_id

    # Starting a new session on same channel cancels previous one
    res = client.post(
        "/channels/1/learning/start",
        json={"is_simulated": False},
        headers=headers,
    )
    assert res.status_code == 201
    new_session_id = res.json()["id"]
    assert new_session_id != session_id

    # Previous session is now cancelled in db
    old_session = db_session.get(LearningSession, uuid.UUID(session_id))
    assert old_session.status == "cancelled"


def test_cancel_learning_session(client, users) -> None:
    alice, _ = users
    headers = auth_header(client, alice.email)

    res = client.post(
        "/channels/2/learning/start",
        json={"is_simulated": True},
        headers=headers,
    )
    assert res.status_code == 201
    session_id = res.json()["id"]

    # Cancel session
    cancel_res = client.post(f"/learning/{session_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # Status is now None (no active session)
    status_res = client.get("/channels/2/learning/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json() is None


def test_channel_validation(client, users) -> None:
    alice, _ = users
    headers = auth_header(client, alice.email)

    # Channel 3 is out of range (ge=1, le=2)
    res = client.post(
        "/channels/3/learning/start",
        json={"is_simulated": True},
        headers=headers,
    )
    assert res.status_code == 422


def test_session_finalization_states(db_session, users) -> None:
    alice, _ = users
    manager = LearningSessionManager(db_session)

    # 1. Ready state (stable data)
    s1 = manager.start_session(channel=1)
    stable_samples = [
        ReadingSample(
            voltage_v=230.0 + (i % 2) * 0.2,
            current_a=0.55 + (i % 2) * 0.01,
            active_power_w=126.0 + (i % 2) * 1.0,
            power_factor=0.98,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(20)
    ]
    session_ready, profile = manager.process_and_finalize_session(
        session_id=s1.id,
        valid_samples=stable_samples,
        excluded_count=1,
        profile_owner=alice,
        profile_name="Stable Motor",
        min_readings=10,
    )
    assert session_ready.status == "ready"
    assert profile is not None
    assert profile.display_name == "Stable Motor"
    assert profile.user_confirmed is False
    assert len(profile.fingerprints) == 1
    assert profile.fingerprints[0].cv_power < 0.1

    # 2. Insufficient data (sample count below threshold)
    s2 = manager.start_session(channel=2)
    session_few, p_few = manager.process_and_finalize_session(
        session_id=s2.id,
        valid_samples=stable_samples[:5],
        min_readings=10,
    )
    assert session_few.status == "insufficient_data"
    assert p_few is None

    # 3. Insufficient data (high excluded fraction: valid fraction < 80%)
    s3 = manager.start_session(channel=2)
    session_bad_ratio, p_bad = manager.process_and_finalize_session(
        session_id=s3.id,
        valid_samples=stable_samples,
        excluded_count=30,  # 20 valid / 50 total = 40% < 80%
        min_readings=10,
    )
    assert session_bad_ratio.status == "insufficient_data"
    assert p_bad is None

    # 4. Unstable load (high CV of power)
    s4 = manager.start_session(channel=1)
    unstable_samples = [
        ReadingSample(
            voltage_v=230.0,
            current_a=0.2 + (i % 3) * 1.5,
            active_power_w=40.0 + (i % 3) * 300.0,  # Swings between 40W and 640W
            power_factor=0.90,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(20)
    ]
    session_unstable, p_unstable = manager.process_and_finalize_session(
        session_id=s4.id,
        valid_samples=unstable_samples,
        min_readings=10,
    )
    assert session_unstable.status == "unstable"
    assert p_unstable is None


def test_profile_crud_and_isolation(client, users) -> None:
    alice, bob = users
    alice_headers = auth_header(client, alice.email)
    bob_headers = auth_header(client, bob.email)

    # Alice creates a profile
    create_res = client.post(
        "/profiles",
        json={
            "display_name": "Alice Induction Fan",
            "channel_last_seen": 1,
            "nominal_power_w": 125.0,
            "nominal_current_a": 0.58,
            "notes": "Table fan in testing lab",
        },
        headers=alice_headers,
    )
    assert create_res.status_code == 201
    profile_id = create_res.json()["id"]

    # Alice lists profiles - sees her fan
    alice_list = client.get("/profiles", headers=alice_headers)
    assert alice_list.status_code == 200
    assert len(alice_list.json()) == 1
    assert alice_list.json()[0]["display_name"] == "Alice Induction Fan"

    # Bob lists profiles - sees empty list (isolation)
    bob_list = client.get("/profiles", headers=bob_headers)
    assert bob_list.status_code == 200
    assert len(bob_list.json()) == 0

    # Bob tries to patch Alice's profile -> 404 (does not leak existence)
    bob_patch = client.patch(
        f"/profiles/{profile_id}",
        json={"display_name": "Hacked Name"},
        headers=bob_headers,
    )
    assert bob_patch.status_code == 404

    # Bob tries to confirm Alice's profile -> 404
    bob_confirm = client.post(
        f"/profiles/{profile_id}/confirm",
        headers=bob_headers,
    )
    assert bob_confirm.status_code == 404

    # Alice patches her own profile
    alice_patch = client.patch(
        f"/profiles/{profile_id}",
        json={"display_name": "Updated Fan Name", "notes": "New notes"},
        headers=alice_headers,
    )
    assert alice_patch.status_code == 200
    assert alice_patch.json()["display_name"] == "Updated Fan Name"
    assert alice_patch.json()["notes"] == "New notes"

    # Alice confirms her profile
    alice_confirm = client.post(
        f"/profiles/{profile_id}/confirm",
        headers=alice_headers,
    )
    assert alice_confirm.status_code == 200
    assert alice_confirm.json()["user_confirmed"] is True
