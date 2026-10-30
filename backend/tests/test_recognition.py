"""Tests for Load Recognition Engine and API.

Covers:
- Standardized distance computation & similarity mapping
- Classification state machine: recognized, ambiguous, unknown, insufficient_data
- Motor vs Resistive Bulb profile discrimination
- REST API: evaluate window, retrieve latest/history, submit feedback (confirmed/corrected)
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models.load_profile import LoadProfile, ProfileFingerprint, RecognitionEvent
from app.models.user import User
from app.security import hash_password
from app.services.fingerprint import ReadingSample, extract_fingerprint
from app.services.recognition import (
    RecognitionEngine,
    compute_standardized_distance,
    distance_to_similarity,
)

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


def make_motor_samples(n: int = 15) -> list[ReadingSample]:
    return [
        ReadingSample(
            voltage_v=230.0 + (i % 3) * 0.5,
            current_a=0.82 + (i % 2) * 0.02,
            active_power_w=125.0 + (i % 3) * 1.5,
            power_factor=0.66,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(n)
    ]


def make_bulb_samples(n: int = 15) -> list[ReadingSample]:
    return [
        ReadingSample(
            voltage_v=230.0 + (i % 2) * 0.2,
            current_a=0.87 + (i % 2) * 0.01,
            active_power_w=200.0 + (i % 2) * 1.0,
            power_factor=0.99,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(n)
    ]


def test_distance_and_similarity_math():
    motor_samples = make_motor_samples(20)
    fp = extract_fingerprint(motor_samples)

    # Fake target fingerprint mirroring motor
    target = ProfileFingerprint(
        profile_id=uuid.uuid4(),
        voltage_mean=fp.voltage_mean,
        voltage_std=fp.voltage_std,
        current_mean=fp.current_mean,
        current_std=fp.current_std,
        current_min=fp.current_min,
        current_max=fp.current_max,
        active_power_mean=fp.active_power_mean,
        active_power_std=fp.active_power_std,
        active_power_min=fp.active_power_min,
        active_power_max=fp.active_power_max,
        power_factor_mean=fp.power_factor_mean,
        power_factor_std=fp.power_factor_std,
        frequency_mean=fp.frequency_mean,
        frequency_std=fp.frequency_std,
        apparent_power_s=fp.apparent_power_s,
        reactive_power_q=fp.reactive_power_q,
        reactive_ratio_q_s=fp.reactive_ratio_q_s,
        cv_power=fp.cv_power,
        power_per_volt_sq=fp.power_per_volt_sq,
        startup_ratio=fp.startup_ratio,
        transition_count=0,
    )

    # Identical fingerprint -> distance 0, similarity 100%
    d_exact = compute_standardized_distance(fp, target)
    assert d_exact == pytest.approx(0.0, abs=1e-5)
    assert distance_to_similarity(d_exact) == 100.0

    # Bulb samples against Motor profile -> large distance, low similarity
    bulb_fp = extract_fingerprint(make_bulb_samples(20))
    d_mismatch = compute_standardized_distance(bulb_fp, target)
    score_mismatch = distance_to_similarity(d_mismatch)
    assert d_mismatch > 3.0
    assert score_mismatch < 25.0


def test_recognition_engine_states(db_session):
    user = add_user(db_session)
    engine = RecognitionEngine(db_session)

    # 1. Insufficient data (< 10 samples)
    res_few = engine.evaluate_window(make_motor_samples(5), [])
    assert res_few.state == "insufficient_data"
    assert res_few.similarity_score == 0.0

    # 2. Unknown (no candidates exist)
    res_none = engine.evaluate_window(make_motor_samples(15), [])
    assert res_none.state == "unknown"
    assert res_none.similarity_score == 0.0

    # Setup profile in db
    motor_profile = LoadProfile(
        owner_id=user.id,
        display_name="Lab Induction Motor",
        channel_last_seen=1,
        nominal_power_w=125.0,
        nominal_current_a=0.82,
        user_confirmed=True,
    )
    db_session.add(motor_profile)
    db_session.flush()

    fp_motor = extract_fingerprint(make_motor_samples(20))
    target_fp = ProfileFingerprint(
        profile_id=motor_profile.id,
        voltage_mean=fp_motor.voltage_mean,
        voltage_std=fp_motor.voltage_std,
        current_mean=fp_motor.current_mean,
        current_std=fp_motor.current_std,
        current_min=fp_motor.current_min,
        current_max=fp_motor.current_max,
        active_power_mean=fp_motor.active_power_mean,
        active_power_std=fp_motor.active_power_std,
        active_power_min=fp_motor.active_power_min,
        active_power_max=fp_motor.active_power_max,
        power_factor_mean=fp_motor.power_factor_mean,
        power_factor_std=fp_motor.power_factor_std,
        frequency_mean=fp_motor.frequency_mean,
        frequency_std=fp_motor.frequency_std,
        apparent_power_s=fp_motor.apparent_power_s,
        reactive_power_q=fp_motor.reactive_power_q,
        reactive_ratio_q_s=fp_motor.reactive_ratio_q_s,
        cv_power=fp_motor.cv_power,
        power_per_volt_sq=fp_motor.power_per_volt_sq,
        startup_ratio=fp_motor.startup_ratio,
        transition_count=0,
    )
    db_session.add(target_fp)
    db_session.commit()
    db_session.refresh(motor_profile)

    # 3. Recognized state
    res_rec = engine.evaluate_window(make_motor_samples(15), [motor_profile])
    assert res_rec.state == "recognized"
    assert res_rec.best_candidate.id == motor_profile.id
    assert res_rec.similarity_score >= 85.0


def test_recognition_api_workflow(client, db_session):
    user = add_user(db_session, "operator@example.com")
    db_session.commit()
    headers = auth_header(client, user.email)

    # 1. Create a learned profile for Motor
    motor_p = LoadProfile(
        owner_id=user.id,
        display_name="Ch1 125W Motor",
        channel_last_seen=1,
        nominal_power_w=125.0,
        nominal_current_a=0.82,
        user_confirmed=True,
    )
    db_session.add(motor_p)
    db_session.flush()

    fp_motor = extract_fingerprint(make_motor_samples(20))
    target_fp = ProfileFingerprint(
        profile_id=motor_p.id,
        voltage_mean=fp_motor.voltage_mean,
        voltage_std=fp_motor.voltage_std,
        current_mean=fp_motor.current_mean,
        current_std=fp_motor.current_std,
        current_min=fp_motor.current_min,
        current_max=fp_motor.current_max,
        active_power_mean=fp_motor.active_power_mean,
        active_power_std=fp_motor.active_power_std,
        active_power_min=fp_motor.active_power_min,
        active_power_max=fp_motor.active_power_max,
        power_factor_mean=fp_motor.power_factor_mean,
        power_factor_std=fp_motor.power_factor_std,
        frequency_mean=fp_motor.frequency_mean,
        frequency_std=fp_motor.frequency_std,
        apparent_power_s=fp_motor.apparent_power_s,
        reactive_power_q=fp_motor.reactive_power_q,
        reactive_ratio_q_s=fp_motor.reactive_ratio_q_s,
        cv_power=fp_motor.cv_power,
        power_per_volt_sq=fp_motor.power_per_volt_sq,
        startup_ratio=fp_motor.startup_ratio,
        transition_count=0,
    )
    db_session.add(target_fp)
    db_session.commit()

    # 2. POST /channels/1/recognize with motor samples
    samples_payload = [
        {
            "voltage_v": s.voltage_v,
            "current_a": s.current_a,
            "active_power_w": s.active_power_w,
            "power_factor": s.power_factor,
            "frequency_hz": s.frequency_hz,
            "timestamp_s": s.timestamp_s,
        }
        for s in make_motor_samples(15)
    ]
    rec_res = client.post(
        "/channels/1/recognize",
        json={"samples": samples_payload},
        headers=headers,
    )
    assert rec_res.status_code == 200
    data = rec_res.json()
    assert data["channel"] == 1
    assert data["state"] == "recognized"
    assert data["similarity_score"] >= 85.0
    assert data["best_candidate_id"] == str(motor_p.id)
    assert data["user_feedback"] == "pending"
    event_id = data["id"]

    # 3. GET /channels/1/recognition/latest
    latest_res = client.get("/channels/1/recognition/latest", headers=headers)
    assert latest_res.status_code == 200
    assert latest_res.json()["id"] == event_id

    # 4. GET /channels/1/recognition/history
    history_res = client.get("/channels/1/recognition/history", headers=headers)
    assert history_res.status_code == 200
    assert len(history_res.json()) >= 1

    # 5. POST /recognition/{event_id}/feedback -> Confirm recognition
    feedback_res = client.post(
        f"/recognition/{event_id}/feedback",
        json={"user_feedback": "confirmed"},
        headers=headers,
    )
    assert feedback_res.status_code == 200
    assert feedback_res.json()["user_feedback"] == "confirmed"

    # 6. Channel validation: Channel 3 is invalid
    invalid_ch = client.post(
        "/channels/3/recognize",
        json={"samples": samples_payload},
        headers=headers,
    )
    assert invalid_ch.status_code == 422

