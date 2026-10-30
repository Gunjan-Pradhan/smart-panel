"""Tests for Optimization Mode Suggestion Rule Engine and APIs.

Covers:
- Declarative YAML rules loading and priority sorting
- Deterministic rule evaluation on Motor, Bulb, and Standby fingerprints
- Automated suggestion generation on session finalization
- REST endpoints: channel suggestions, profile suggestions, accept suggestion
- Operator-in-the-loop confirmation and multi-tenant isolation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models.load_profile import (
    LearningSession,
    LoadModeSelection,
    LoadProfile,
    ModeSuggestion,
    ProfileFingerprint,
)
from app.models.user import User
from app.security import hash_password
from app.services.fingerprint import ReadingSample
from app.services.learning_manager import LearningSessionManager
from app.services.mode_suggester import (
    ModeSuggester,
    evaluate_fingerprint_against_rule,
    load_rules,
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


def test_yaml_rules_loading():
    rules = load_rules()
    assert len(rules) >= 4
    rule_ids = [r.id for r in rules]
    assert "RULE_MOTOR_PROTECTION" in rule_ids
    assert "RULE_RESISTIVE_LIGHTING_ECO" in rule_ids
    assert "RULE_STANDBY_BASELINE" in rule_ids

    # Verify priority sorting
    priorities = [r.priority for r in rules]
    assert priorities == sorted(priorities)


def test_rule_evaluation_on_motor_and_bulb():
    rules = load_rules()
    motor_rule = next(r for r in rules if r.id == "RULE_MOTOR_PROTECTION")
    eco_rule = next(r for r in rules if r.id == "RULE_RESISTIVE_LIGHTING_ECO")
    standby_rule = next(r for r in rules if r.id == "RULE_STANDBY_BASELINE")

    # Synthetic Motor Fingerprint
    motor_fp = ProfileFingerprint(
        profile_id=uuid.uuid4(),
        voltage_mean=230.0,
        voltage_std=0.5,
        current_mean=0.82,
        current_std=0.01,
        current_min=0.80,
        current_max=0.85,
        active_power_mean=125.0,
        active_power_std=1.0,
        active_power_min=123.0,
        active_power_max=127.0,
        power_factor_mean=0.66,
        power_factor_std=0.01,
        frequency_mean=50.0,
        frequency_std=0.02,
        apparent_power_s=188.6,
        reactive_power_q=141.6,
        reactive_ratio_q_s=0.75,
        cv_power=0.01,
        power_per_volt_sq=0.00236,
        startup_ratio=3.5,
        transition_count=0,
    )

    matches_motor, values_motor = evaluate_fingerprint_against_rule(motor_fp, motor_rule)
    assert matches_motor is True
    assert values_motor["power_factor"] == 0.66
    assert values_motor["active_power_w"] == 125.0

    # Motor does not match Eco rule (PF 0.66 < 0.95)
    matches_eco_on_motor, _ = evaluate_fingerprint_against_rule(motor_fp, eco_rule)
    assert matches_eco_on_motor is False

    # Synthetic Bulb Fingerprint
    bulb_fp = ProfileFingerprint(
        profile_id=uuid.uuid4(),
        voltage_mean=230.0,
        voltage_std=0.2,
        current_mean=0.87,
        current_std=0.01,
        current_min=0.86,
        current_max=0.88,
        active_power_mean=200.0,
        active_power_std=0.5,
        active_power_min=199.0,
        active_power_max=201.0,
        power_factor_mean=0.99,
        power_factor_std=0.005,
        frequency_mean=50.0,
        frequency_std=0.01,
        apparent_power_s=200.1,
        reactive_power_q=6.3,
        reactive_ratio_q_s=0.03,
        cv_power=0.003,
        power_per_volt_sq=0.00378,
        startup_ratio=1.2,
        transition_count=0,
    )

    matches_bulb, values_bulb = evaluate_fingerprint_against_rule(bulb_fp, eco_rule)
    assert matches_bulb is True
    assert values_bulb["power_factor"] == 0.99

    # Standby low-power baseline
    standby_fp = ProfileFingerprint(
        profile_id=uuid.uuid4(),
        voltage_mean=230.0,
        voltage_std=0.1,
        current_mean=0.04,
        current_std=0.001,
        current_min=0.038,
        current_max=0.042,
        active_power_mean=8.5,
        active_power_std=0.1,
        active_power_min=8.3,
        active_power_max=8.7,
        power_factor_mean=0.92,
        power_factor_std=0.01,
        frequency_mean=50.0,
        frequency_std=0.01,
        apparent_power_s=9.2,
        reactive_power_q=3.5,
        reactive_ratio_q_s=0.38,
        cv_power=0.01,
        power_per_volt_sq=0.00016,
        startup_ratio=1.0,
        transition_count=0,
    )
    matches_standby, _ = evaluate_fingerprint_against_rule(standby_fp, standby_rule)
    assert matches_standby is True
    assert standby_rule.proposed_settings["switchable"] is False


def test_automated_suggestions_on_session_finalization(db_session):
    user = add_user(db_session, "operator1@example.com")
    db_session.commit()
    manager = LearningSessionManager(db_session)

    session = manager.start_session(channel=1)

    # Samples simulating 125W motor
    motor_samples = [
        ReadingSample(
            voltage_v=230.0,
            current_a=0.82,
            active_power_w=125.0,
            power_factor=0.66,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(20)
    ]

    ready_session, profile = manager.process_and_finalize_session(
        session_id=session.id,
        valid_samples=motor_samples,
        profile_owner=user,
        profile_name="Workshop Induction Motor",
        min_readings=10,
    )

    assert ready_session.status == "ready"
    assert profile is not None

    # Check that ModeSuggestions were automatically generated in the database
    suggester = ModeSuggester(db_session)
    suggestions = suggester.get_suggestions_by_session(session.id)
    assert len(suggestions) >= 1
    motor_suggestion = next(s for s in suggestions if s.mode_name == "protection")
    assert motor_suggestion.rule_id == "RULE_MOTOR_PROTECTION"
    assert "Inductive motor load detected" in motor_suggestion.reason_text


def test_suggestions_api_and_accept_flow(client, db_session):
    alice = add_user(db_session, "alice@example.com")
    bob = add_user(db_session, "bob@example.com")
    db_session.commit()

    headers = auth_header(client, alice.email)
    bob_headers = auth_header(client, bob.email)

    # 1. Finalize a bulb session for Alice on Channel 2
    manager = LearningSessionManager(db_session)
    session = manager.start_session(channel=2)
    bulb_samples = [
        ReadingSample(
            voltage_v=230.0,
            current_a=0.87,
            active_power_w=200.0,
            power_factor=0.99,
            frequency_hz=50.0,
            timestamp_s=1700000000.0 + i,
        )
        for i in range(20)
    ]
    ready_s, profile = manager.process_and_finalize_session(
        session_id=session.id,
        valid_samples=bulb_samples,
        profile_owner=alice,
        profile_name="Living Room Bulbs",
        min_readings=10,
    )

    # 2. GET /channels/2/suggestions
    ch_res = client.get("/channels/2/suggestions", headers=headers)
    assert ch_res.status_code == 200
    suggestions = ch_res.json()
    assert len(suggestions) >= 1
    eco_sug = next(s for s in suggestions if s["mode_name"] == "eco")
    assert eco_sug["rule_id"] == "RULE_RESISTIVE_LIGHTING_ECO"
    sug_id = eco_sug["id"]

    # 3. GET /profiles/{id}/suggestions
    prof_res = client.get(f"/profiles/{profile.id}/suggestions", headers=headers)
    assert prof_res.status_code == 200
    assert len(prof_res.json()) >= 1

    # Bob cannot read Alice's profile suggestions (isolation -> 404)
    bob_res = client.get(f"/profiles/{profile.id}/suggestions", headers=bob_headers)
    assert bob_res.status_code == 404

    # 4. Operator accepts suggestion: POST /suggestions/{id}/accept
    accept_res = client.post(f"/suggestions/{sug_id}/accept", headers=headers)
    assert accept_res.status_code == 200
    sel_data = accept_res.json()
    assert sel_data["profile_id"] == str(profile.id)
    assert sel_data["mode_name"] == "eco"
    assert sel_data["enabled"] is True
    assert sel_data["source"] == "ai_suggestion"

    # 5. Check active modes: GET /profiles/{id}/modes
    modes_res = client.get(f"/profiles/{profile.id}/modes", headers=headers)
    assert modes_res.status_code == 200
    modes = modes_res.json()
    assert len(modes) == 1
    assert modes[0]["mode_name"] == "eco"
    assert modes[0]["enabled"] is True

