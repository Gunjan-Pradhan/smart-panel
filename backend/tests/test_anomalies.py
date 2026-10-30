"""Tests for Anomaly Detection Engine and REST API.

Covers:
- Rolling Z-score calculation with noise floor protection
- Multi-tier severity classification (info, warning, critical)
- DOL motor startup transient inrush filtering
- Scikit-learn Isolation Forest multivariate scoring
- PostgreSQL event logging and REST API validation
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
from app.models.load_profile import LoadProfile, ProfileFingerprint
from app.models.user import User
from app.security import hash_password
from app.services.anomaly_detector import (
    AnomalyDetector,
    IsolationForestScorer,
    calculate_z_scores,
)
from app.services.fingerprint import ReadingSample

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


def make_motor_fingerprint(profile_id: uuid.UUID) -> ProfileFingerprint:
    return ProfileFingerprint(
        profile_id=profile_id,
        voltage_mean=230.0,
        voltage_std=0.0,  # Zero variance in test to test noise floor protection!
        current_mean=0.82,
        current_std=0.0,  # Zero variance
        current_min=0.82,
        current_max=0.82,
        active_power_mean=125.0,
        active_power_std=0.0,
        active_power_min=125.0,
        active_power_max=125.0,
        power_factor_mean=0.66,
        power_factor_std=0.0,
        frequency_mean=50.0,
        frequency_std=0.0,
        apparent_power_s=189.4,
        reactive_power_q=142.2,
        reactive_ratio_q_s=0.75,
        cv_power=0.0,
        power_per_volt_sq=0.00236,
        startup_ratio=4.0,
        transition_count=0,
    )


def test_z_score_math_and_noise_floor():
    fp = make_motor_fingerprint(uuid.uuid4())

    # 1. Nominal sample -> Z near zero, no flags
    nominal = ReadingSample(
        voltage_v=230.0,
        current_a=0.82,
        active_power_w=125.0,
        power_factor=0.66,
        frequency_hz=50.0,
    )
    z_nom, flags_nom = calculate_z_scores(nominal, fp)
    assert z_nom.max_z == 0.0
    assert len(flags_nom) == 0

    # 2. Overcurrent beyond warning threshold
    # Current noise floor is 0.05A. Deviation of +0.15A => Z = 0.15 / 0.05 = 3.0
    mild_overcurrent = ReadingSample(
        voltage_v=230.0,
        current_a=0.97,
        active_power_w=125.0,
        power_factor=0.66,
        frequency_hz=50.0,
    )
    z_mild, flags_mild = calculate_z_scores(mild_overcurrent, fp)
    assert z_mild.z_current == pytest.approx(3.0, abs=0.1)
    assert "overcurrent" in flags_mild

    # 3. Severe critical overload (Z >= 4.0)
    critical_sample = ReadingSample(
        voltage_v=230.0,
        current_a=2.00,  # Delta = 1.18A => Z = 1.18 / 0.05 = 23.6
        active_power_w=300.0,
        power_factor=0.66,
        frequency_hz=50.0,
    )
    z_crit, flags_crit = calculate_z_scores(critical_sample, fp)
    assert z_crit.max_z >= 4.0
    assert "overcurrent" in flags_crit
    assert "overpower" in flags_crit


def test_transient_inrush_suppression():
    detector = AnomalyDetector()
    fp = make_motor_fingerprint(uuid.uuid4())

    # Inrush sample: high current during motor direct-on-line start
    inrush_sample = ReadingSample(
        voltage_v=228.0,
        current_a=3.50,  # 4.2x nominal
        active_power_w=450.0,
        power_factor=0.60,
        frequency_hz=50.0,
    )

    # 1. During startup window: suppressed as info / transient_inrush
    res_inrush = detector.evaluate_sample(
        inrush_sample,
        fp,
        is_startup_window=True,
    )
    assert res_inrush.is_transient_inrush is True
    assert res_inrush.severity == "info"
    assert res_inrush.is_anomaly is False

    # 2. During steady state: flagged as critical overcurrent
    res_steady = detector.evaluate_sample(
        inrush_sample,
        fp,
        is_startup_window=False,
    )
    assert res_steady.is_transient_inrush is False
    assert res_steady.severity == "critical"
    assert res_steady.is_anomaly is True


def test_isolation_forest_scoring():
    scorer = IsolationForestScorer(contamination=0.1, random_state=42)

    # Generate normal baseline data
    normal_samples = [
        ReadingSample(
            voltage_v=230.0 + (i % 3) * 0.5,
            current_a=0.82 + (i % 2) * 0.02,
            active_power_w=125.0 + (i % 3) * 1.0,
            power_factor=0.66 + (i % 2) * 0.01,
            frequency_hz=50.0,
        )
        for i in range(30)
    ]
    scorer.fit(normal_samples)
    assert scorer.is_fitted is True

    # Normal point yields higher normality score than outlier point
    normal_point = ReadingSample(
        voltage_v=230.2,
        current_a=0.83,
        active_power_w=125.5,
        power_factor=0.66,
        frequency_hz=50.0,
    )
    outlier_point = ReadingSample(
        voltage_v=180.0,
        current_a=4.50,
        active_power_w=600.0,
        power_factor=0.40,
        frequency_hz=50.0,
    )
    normal_score = scorer.score(normal_point)
    outlier_score = scorer.score(outlier_point)
    assert normal_score is not None
    assert outlier_score is not None
    assert normal_score > outlier_score


def test_anomalies_api_workflow(client, db_session):
    user = add_user(db_session, "user@example.com")
    device = add_device(db_session, user)

    # Create profile on Channel 1
    motor_p = LoadProfile(
        owner_id=user.id,
        display_name="Induction Motor 125W",
        channel_last_seen=1,
        nominal_power_w=125.0,
        nominal_current_a=0.82,
        user_confirmed=True,
    )
    db_session.add(motor_p)
    db_session.flush()

    fp = make_motor_fingerprint(motor_p.id)
    db_session.add(fp)
    db_session.commit()

    headers = auth_header(client, user.email)

    # 1. Normal check
    res_normal = client.post(
        "/channels/1/anomalies/check",
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
    assert res_normal.status_code == 200
    body_nom = res_normal.json()
    assert body_nom["is_anomaly"] is False
    assert body_nom["severity"] == "info"

    # 2. Critical anomaly check -> Should record event in events table
    res_crit = client.post(
        "/channels/1/anomalies/check",
        json={
            "sample": {
                "voltage_v": 230.0,
                "current_a": 3.80,  # Severe stall current
                "active_power_w": 550.0,
                "power_factor": 0.66,
                "frequency_hz": 50.0,
            },
            "is_startup_window": False,
        },
        headers=headers,
    )
    assert res_crit.status_code == 200
    body_crit = res_crit.json()
    assert body_crit["is_anomaly"] is True
    assert body_crit["severity"] == "critical"
    assert "overcurrent" in body_crit["flags"]

    # 3. Retrieve logged anomaly events
    events_res = client.get("/channels/1/anomalies/events", headers=headers)
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 1
    assert events[0]["severity"] == "critical"
    assert "overcurrent" in events[0]["type"]

    # 4. Channel 3 validation
    res_invalid_ch = client.post(
        "/channels/3/anomalies/check",
        json={
            "sample": {
                "voltage_v": 230.0,
                "current_a": 0.82,
                "active_power_w": 125.0,
                "power_factor": 0.66,
            }
        },
        headers=headers,
    )
    assert res_invalid_ch.status_code == 422
