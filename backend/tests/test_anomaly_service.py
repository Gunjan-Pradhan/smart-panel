"""Tests for Workstream 8: Anomaly Detection & Health Score.

Verifies:
1.  fit_isolation_forest returns False when fewer than 10 fingerprints exist.
2.  fit_isolation_forest fits and saves a .joblib file when enough data is provided.
3.  score_reading returns a float in [0, 100] for a normal reading.
4.  score_reading returns a lower score for a clearly anomalous reading.
5.  score_reading returns None when no model file is present.
6.  GET /profiles/{id}/health_score returns 400 when model is not ready.
7.  GET /profiles/{id}/health_score returns 404 for another user's profile.
8.  GET /profiles/{id}/health_score returns a score when the model IS ready (mocked).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.auth import limiter
from app.db.session import get_db
from app.main import app
from app.models import Device, User
from app.models.load_profile import LoadProfile, ProfileFingerprint
from app.security import hash_password
from app.services.anomaly_service import (
    _model_path,
    fit_isolation_forest,
    score_reading,
)
from app.services.fingerprint import ReadingSample

PASSWORD = "CorrectHorseBattery1"
PASSWORD_HASH = hash_password(PASSWORD)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def add_user(db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=PASSWORD_HASH,
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def auth_header(client: TestClient, email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
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


def _make_profile_with_fingerprints(db_session, owner: User, n: int) -> LoadProfile:
    """Create a LoadProfile with n synthetic ProfileFingerprint rows."""
    profile = LoadProfile(
        owner_id=owner.id,
        display_name=f"Test Profile ({n} fps)",
        channel_last_seen=1,
    )
    db_session.add(profile)
    db_session.flush()

    rng = np.random.default_rng(seed=42)
    for _ in range(n):
        fp = ProfileFingerprint(
            profile_id=profile.id,
            # Normal 230 V, ~5 A, ~1150 W, PF 0.95 ± small noise
            voltage_mean=float(rng.normal(230, 2)),
            voltage_std=float(rng.uniform(0.5, 2.0)),
            current_mean=float(rng.normal(5.0, 0.2)),
            current_std=float(rng.uniform(0.05, 0.3)),
            current_min=4.5,
            current_max=5.5,
            active_power_mean=float(rng.normal(1150, 20)),
            active_power_std=float(rng.uniform(5, 20)),
            active_power_min=1100.0,
            active_power_max=1200.0,
            power_factor_mean=float(rng.normal(0.95, 0.01)),
            power_factor_std=0.01,
            frequency_mean=50.0,
            frequency_std=0.1,
            apparent_power_s=1210.0,
            reactive_power_q=100.0,
            reactive_ratio_q_s=0.08,
            cv_power=0.02,
            power_per_volt_sq=0.022,
            transition_count=0,
        )
        db_session.add(fp)

    db_session.commit()
    db_session.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# Unit tests for anomaly_service functions
# ---------------------------------------------------------------------------


def test_fit_isolation_forest_too_few_samples(db_session):
    """fit_isolation_forest returns False when < 10 fingerprints exist."""
    owner = add_user(db_session, "anom_few@example.com")
    profile = _make_profile_with_fingerprints(db_session, owner, n=5)

    result = fit_isolation_forest(profile.id, db_session)
    assert result is False
    # No model file should be written
    assert not _model_path(profile.id).exists()


def test_fit_isolation_forest_enough_samples(db_session, tmp_path):
    """fit_isolation_forest returns True and writes a .joblib file with ≥10 fingerprints."""
    owner = add_user(db_session, "anom_ok@example.com")
    profile = _make_profile_with_fingerprints(db_session, owner, n=15)

    # Patch data directory so we don't pollute the real one during tests
    patched_path = tmp_path / f"{profile.id}.joblib"
    with patch("app.services.anomaly_service._model_path", return_value=patched_path):
        # Also clear LRU cache between runs
        from app.services.anomaly_service import _load_model
        _load_model.cache_clear()

        result = fit_isolation_forest(profile.id, db_session)

    assert result is True
    assert patched_path.exists()


def test_score_reading_normal(tmp_path):
    """score_reading returns a float in [0, 100] for a normal-looking reading."""
    # Train a fresh model on synthetic normal data
    from sklearn.ensemble import IsolationForest
    import joblib
    import numpy as np

    rng = np.random.default_rng(42)
    X_train = rng.normal([230, 5, 1150, 0.95], [2, 0.2, 20, 0.01], size=(50, 4))
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X_train)

    model_file = tmp_path / "test_model.joblib"
    joblib.dump(model, model_file)

    # Clear LRU cache so it loads the new file
    from app.services.anomaly_service import _load_model
    _load_model.cache_clear()

    normal_reading = ReadingSample(
        voltage_v=230.0,
        current_a=5.0,
        active_power_w=1150.0,
        power_factor=0.95,
        frequency_hz=50.0,
    )
    score = score_reading(normal_reading, model_file)
    assert score is not None
    assert 0.0 <= score <= 100.0


def test_score_reading_anomalous_lower_than_normal(tmp_path):
    """An anomalous reading should produce a lower health score than a normal one."""
    from sklearn.ensemble import IsolationForest
    import joblib
    import numpy as np

    rng = np.random.default_rng(42)
    X_train = rng.normal([230, 5, 1150, 0.95], [2, 0.2, 20, 0.01], size=(60, 4))
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X_train)

    model_file = tmp_path / "anom_model.joblib"
    joblib.dump(model, model_file)

    from app.services.anomaly_service import _load_model
    _load_model.cache_clear()

    normal = ReadingSample(voltage_v=230, current_a=5, active_power_w=1150,
                           power_factor=0.95, frequency_hz=50)
    anomalous = ReadingSample(voltage_v=180, current_a=25, active_power_w=4500,
                              power_factor=0.3, frequency_hz=55)

    score_normal = score_reading(normal, model_file)
    score_anomalous = score_reading(anomalous, model_file)

    assert score_normal is not None
    assert score_anomalous is not None
    assert score_anomalous < score_normal, (
        f"Expected anomalous score ({score_anomalous}) < normal score ({score_normal})"
    )


def test_score_reading_no_model(tmp_path):
    """score_reading returns None when no model file exists."""
    from app.services.anomaly_service import _load_model
    _load_model.cache_clear()

    missing = tmp_path / "nonexistent.joblib"
    reading = ReadingSample(voltage_v=230, current_a=5, active_power_w=1150,
                            power_factor=0.95, frequency_hz=50)
    result = score_reading(reading, missing)
    assert result is None


# ---------------------------------------------------------------------------
# API endpoint tests (GET /profiles/{id}/health_score)
# ---------------------------------------------------------------------------


SAMPLE_PAYLOAD = {
    "sample": {
        "voltage_v": 230.0,
        "current_a": 5.0,
        "active_power_w": 1150.0,
        "power_factor": 0.95,
        "frequency_hz": 50.0,
    }
}


def test_health_score_model_not_ready(client, db_session):
    """Returns 400 when the profile has fewer than 10 fingerprints."""
    owner = add_user(db_session, "hs_notready@example.com")
    profile = _make_profile_with_fingerprints(db_session, owner, n=3)
    db_session.commit()

    hdr = auth_header(client, owner.email)
    resp = client.post(f"/profiles/{profile.id}/health_score",
                       json=SAMPLE_PAYLOAD, headers=hdr)
    assert resp.status_code == 400
    assert "10" in resp.json()["detail"] or "ready" in resp.json()["detail"]


def test_health_score_other_user_profile_404(client, db_session):
    """Returns 404 (not 403) for another user's profile — tenant isolation Rule 6."""
    owner = add_user(db_session, "hs_owner@example.com")
    attacker = add_user(db_session, "hs_attacker@example.com")
    profile = _make_profile_with_fingerprints(db_session, owner, n=15)
    db_session.commit()

    hdr = auth_header(client, attacker.email)
    resp = client.post(f"/profiles/{profile.id}/health_score",
                       json=SAMPLE_PAYLOAD, headers=hdr)
    assert resp.status_code == 404


def test_health_score_returns_score(client, db_session):
    """Returns a valid health_score when model is available (mocked)."""
    owner = add_user(db_session, "hs_scored@example.com")
    profile = _make_profile_with_fingerprints(db_session, owner, n=15)
    db_session.commit()

    hdr = auth_header(client, owner.email)

    # Mock get_health_score_for_profile to avoid actual disk I/O in test
    with patch(
        "app.api.learning.get_health_score_for_profile",
        return_value=82.5,
    ):
        resp = client.post(
            f"/profiles/{profile.id}/health_score",
            json=SAMPLE_PAYLOAD,
            headers=hdr,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["health_score"] == 82.5
    assert str(profile.id) == data["profile_id"]
    assert "SIMULATED" in data["note"]

