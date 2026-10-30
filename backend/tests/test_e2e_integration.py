"""Comprehensive End-to-End (E2E) Integration Test.

Simulates the complete system lifecycle:
1. User registration, authentication, device setup.
2. Ingestion of raw telemetry via MQTT adapter into TimescaleDB.
3. Machine learning session execution and statistical fingerprint extraction.
4. Declarative rule engine optimization mode suggestion (Protection & Eco modes).
5. Operator acceptance and profile confirmation.
6. Real-time load recognition and operator feedback loop.
7. Anomaly detection with Z-score stall alerts and DOL inrush transient suppression.
8. Command validation with Always-On safety guard.
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
from app.models.channel import Channel
from app.models.device import Device
from app.models.event import Event
from app.models.load_profile import (
    LearningSession,
    LoadModeSelection,
    LoadProfile,
    ModeSuggestion,
    ProfileFingerprint,
    RecognitionEvent,
)
from app.models.telemetry import Telemetry
from app.models.user import User
from app.security import hash_password
from app.services.fingerprint import ReadingSample
from app.services.ingestion import TelemetryIngestionService
from app.services.learning_manager import LearningSessionManager
from app.services.mqtt_adapter import MQTTTelemetryAdapter

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


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


def make_motor_samples(n: int = 20) -> list[ReadingSample]:
    return [
        ReadingSample(
            voltage_v=230.0 + (i % 2) * 0.4,
            current_a=0.82 + (i % 2) * 0.01,
            active_power_w=125.0 + (i % 2) * 1.0,
            power_factor=0.66,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(n)
    ]


def make_bulb_samples(n: int = 20) -> list[ReadingSample]:
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


def test_full_system_e2e_lifecycle(client, db_session):
    # -------------------------------------------------------------------------
    # 1. Setup User and Panel Device with Dual Channels
    # -------------------------------------------------------------------------
    operator = User(
        email="final_project_lead@example.com",
        password_hash=PASSWORD_HASH,
        role="operator",
        is_active=True,
    )
    db_session.add(operator)
    db_session.flush()

    panel = Device(
        device_id="PANEL-0001",
        name="Smart Load Protection Panel Prototype",
        owner_id=operator.id,
    )
    db_session.add(panel)
    db_session.flush()

    ch1 = Channel(device_pk=panel.id, ch=1, name="Circuit 1 - Industrial Motor")
    ch2 = Channel(device_pk=panel.id, ch=2, name="Circuit 2 - Household Bulbs")
    db_session.add(ch1)
    db_session.add(ch2)
    db_session.commit()

    # Authenticate and acquire JWT
    login_res = client.post(
        "/auth/login",
        json={"email": operator.email, "password": PASSWORD},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # -------------------------------------------------------------------------
    # 2. Ingest MQTT Telemetry into TimescaleDB
    # -------------------------------------------------------------------------
    adapter = MQTTTelemetryAdapter()
    ingest_svc = TelemetryIngestionService(db_session)

    # Firmware publishes topic per metric: e.g. energy/dual_pzem/circuit1/voltage_V
    parsed = adapter.parse_topic("energy/dual_pzem/circuit1/voltage_V", "230.2")
    assert parsed is not None
    assert parsed.channel == 1
    assert parsed.metric_name == "voltage_V"
    assert parsed.value == 230.2

    # Build and ingest full validated telemetry record
    record = adapter.build_record(
        channel=1,
        v=230.2,
        i=0.825,
        p=125.4,
        pf=0.66,
        f=50.0,
        energy_kwh=0.045,
    )
    assert record.validity == "valid"

    telemetry_db = ingest_svc.ingest_record(record, device_id="PANEL-0001")
    assert telemetry_db is not None
    assert float(telemetry_db.v) == 230.2
    assert float(telemetry_db.i) == 0.825
    assert float(telemetry_db.p) == 125.4

    # -------------------------------------------------------------------------
    # 3. Learning Session & Fingerprint Extraction on Channel 1 (Motor)
    # -------------------------------------------------------------------------
    start_res = client.post(
        "/channels/1/learning/start",
        json={"is_simulated": True},
        headers=headers,
    )
    assert start_res.status_code == 201
    session_id = uuid.UUID(start_res.json()["id"])

    # Finalize learning session with clean motor telemetry
    manager = LearningSessionManager(db_session)
    ready_session, motor_profile = manager.process_and_finalize_session(
        session_id=session_id,
        valid_samples=make_motor_samples(20),
        profile_owner=operator,
        profile_name="125W Single-Phase Motor",
        min_readings=10,
    )
    assert ready_session.status == "ready"
    assert motor_profile is not None
    assert float(motor_profile.nominal_power_w) == pytest.approx(125.5, abs=1.0)
    assert float(motor_profile.nominal_current_a) == pytest.approx(0.825, abs=0.05)

    # -------------------------------------------------------------------------
    # 4. Declarative Rule Engine Suggestions & Operator Acceptance
    # -------------------------------------------------------------------------
    sug_res = client.get("/channels/1/suggestions", headers=headers)
    assert sug_res.status_code == 200
    suggestions = sug_res.json()
    assert len(suggestions) >= 1
    motor_sug = next(s for s in suggestions if s["mode_name"] == "protection")
    assert motor_sug["rule_id"] == "RULE_MOTOR_PROTECTION"
    assert "Inductive motor load detected" in motor_sug["reason_text"]

    # Operator explicitly accepts Protection Mode
    accept_res = client.post(
        f"/suggestions/{motor_sug['id']}/accept",
        headers=headers,
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["mode_name"] == "protection"
    assert accept_res.json()["enabled"] is True

    # Operator confirms learned profile
    confirm_res = client.post(
        f"/profiles/{motor_profile.id}/confirm",
        headers=headers,
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["user_confirmed"] is True

    # -------------------------------------------------------------------------
    # 5. Live Load Recognition & Operator Feedback
    # -------------------------------------------------------------------------
    live_window = [
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
        json={"samples": live_window},
        headers=headers,
    )
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert rec_data["state"] == "recognized"
    assert rec_data["similarity_score"] >= 85.0
    assert rec_data["best_candidate_id"] == str(motor_profile.id)

    # Submit feedback: operator confirms recognition
    fb_res = client.post(
        f"/recognition/{rec_data['id']}/feedback",
        json={"user_feedback": "confirmed"},
        headers=headers,
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["user_feedback"] == "confirmed"

    # -------------------------------------------------------------------------
    # 6. Anomaly Detection: Inrush Suppression vs Rotor Stall Alert
    # -------------------------------------------------------------------------
    # DOL inrush surge (3.2A) during startup window -> suppressed as info
    inrush_res = client.post(
        "/channels/1/anomalies/check",
        json={
            "sample": {
                "voltage_v": 228.0,
                "current_a": 3.20,
                "active_power_w": 420.0,
                "power_factor": 0.60,
                "frequency_hz": 50.0,
            },
            "is_startup_window": True,
        },
        headers=headers,
    )
    assert inrush_res.status_code == 200
    assert inrush_res.json()["is_transient_inrush"] is True
    assert inrush_res.json()["severity"] == "info"

    # Sustained mechanical stall overload (3.5A) in steady-state -> critical alert
    stall_res = client.post(
        "/channels/1/anomalies/check",
        json={
            "sample": {
                "voltage_v": 227.0,
                "current_a": 3.50,
                "active_power_w": 480.0,
                "power_factor": 0.60,
                "frequency_hz": 50.0,
            },
            "is_startup_window": False,
        },
        headers=headers,
    )
    assert stall_res.status_code == 200
    assert stall_res.json()["severity"] == "critical"
    assert stall_res.json()["is_anomaly"] is True

    # Verify event was persisted to PostgreSQL events table
    events_res = client.get("/channels/1/anomalies/events", headers=headers)
    assert events_res.status_code == 200
    assert len(events_res.json()) >= 1
    assert events_res.json()[0]["severity"] == "critical"

    # -------------------------------------------------------------------------
    # 7. Mode Enforcement: Command Validation & Always-On Safety Net
    # -------------------------------------------------------------------------
    # Also add always_on mode to test accidental cutoff guard
    mode_ao = LoadModeSelection(
        profile_id=motor_profile.id,
        mode_name="always_on",
        enabled=True,
        source="manual",
        selected_by=operator.id,
    )
    db_session.add(mode_ao)
    db_session.commit()

    # Unforced OFF command rejected
    v_reject = client.post(
        "/channels/1/commands/validate",
        json={"action": "OFF", "force": False},
        headers=headers,
    )
    assert v_reject.status_code == 200
    assert v_reject.json()["allowed"] is False
    assert "Always-On baseline mode" in v_reject.json()["reason"]

    # Forced OFF command allowed
    v_allow = client.post(
        "/channels/1/commands/validate",
        json={"action": "OFF", "force": True},
        headers=headers,
    )
    assert v_allow.status_code == 200
    assert v_allow.json()["allowed"] is True
