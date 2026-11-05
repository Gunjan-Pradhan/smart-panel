"""Anomaly Service — Workstream 8: Persistent IsolationForest & Health Score.

This module exposes two public functions:

fit_isolation_forest(profile_id, db)
    Fits a fresh IsolationForest on the fingerprint vectors stored in the DB
    for a given profile, then saves the model to
    backend/data/models/<profile_id>.joblib so it survives server restarts.
    Returns True on success, False if there are not enough data points.

score_reading(reading, model_path)
    Loads the persisted model (or uses an in-memory LRU cache) and returns a
    health score in [0, 100].
        • 100 = reading looks completely normal
        • 0   = very anomalous (Isolation Forest calls it an outlier)

Health score formula
    raw = isolation_forest.decision_function(sample)   # higher = more normal
    normalised to [0, 1] using a fixed sigmoid-like mapping, then × 100.

    In practice scikit-learn's decision_function returns values roughly in
    [-0.5, 0.5] for a well-tuned forest, so we use:
        health = clamp(100 × (raw + 0.5) / 1.0, 0, 100)

    If the model is not available, the function returns None to signal "no
    model yet" so the caller can respond with a 400 or a sensible default.
"""

from __future__ import annotations

import logging
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.models.load_profile import LoadProfile, ProfileFingerprint
from app.services.fingerprint import ReadingSample

logger = logging.getLogger(__name__)

# Directory where serialized models are stored (created if absent)
_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "models"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Feature vector — 4 electrical parameters used for multivariate scoring
_FEATURES = ["voltage_v", "current_a", "active_power_w", "power_factor"]

# IsolationForest hyper-parameters
_N_ESTIMATORS = 100
_CONTAMINATION = 0.05
_RANDOM_STATE = 42

# Minimum number of fingerprint samples needed to fit a meaningful model
_MIN_SAMPLES = 10


def _model_path(profile_id: uuid.UUID) -> Path:
    """Return the filesystem path for a profile's persisted model."""
    return _DATA_DIR / f"{profile_id}.joblib"


def _fingerprint_to_vector(fp: ProfileFingerprint) -> list[float]:
    """Convert a ProfileFingerprint row to a 4-element feature vector.

    We use the *mean* values from the fingerprint as the representative
    sample for training.  This gives the forest knowledge of the normal
    operating range even when raw PZEM samples are not stored.
    """
    return [
        fp.voltage_mean,
        fp.current_mean,
        fp.active_power_mean,
        fp.power_factor_mean,
    ]


def fit_isolation_forest(profile_id: uuid.UUID, db: Session) -> bool:
    """Fit a fresh IsolationForest on all fingerprints for *profile_id*.

    Args:
        profile_id: UUID of the LoadProfile to train on.
        db: SQLAlchemy session (read-only usage).

    Returns:
        True  — model fitted and saved to disk.
        False — not enough data to fit (< _MIN_SAMPLES fingerprints).
    """
    import joblib

    profile = db.get(LoadProfile, profile_id)
    if profile is None:
        logger.warning("fit_isolation_forest: profile %s not found", profile_id)
        return False

    fingerprints = profile.fingerprints
    if len(fingerprints) < _MIN_SAMPLES:
        logger.info(
            "fit_isolation_forest: only %d fingerprint(s) for profile %s "
            "(need %d) — skipping",
            len(fingerprints),
            profile_id,
            _MIN_SAMPLES,
        )
        return False

    X = np.array([_fingerprint_to_vector(fp) for fp in fingerprints])

    model = IsolationForest(
        n_estimators=_N_ESTIMATORS,
        contamination=_CONTAMINATION,
        random_state=_RANDOM_STATE,
    )
    model.fit(X)

    path = _model_path(profile_id)
    joblib.dump(model, path)

    # Invalidate LRU cache so the next score call loads the fresh model
    _load_model.cache_clear()

    logger.info(
        "fit_isolation_forest: fitted on %d samples for profile %s → %s",
        len(fingerprints),
        profile_id,
        path,
    )
    return True


@lru_cache(maxsize=32)
def _load_model(model_path: str) -> Optional[IsolationForest]:
    """Load and cache a persisted IsolationForest model.

    Returns None if the file does not exist.
    LRU-cached by path so repeated calls don't incur disk I/O.
    """
    import joblib

    if not os.path.exists(model_path):
        return None
    try:
        return joblib.load(model_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load model from %s: %s", model_path, exc)
        return None


def score_reading(
    reading: ReadingSample,
    model_path: Path,
) -> Optional[float]:
    """Score a single reading and return a health score in [0, 100].

    Args:
        reading:    One electrical reading to evaluate.
        model_path: Path to the persisted .joblib model file.

    Returns:
        A float in [0.0, 100.0] where 100 = perfectly normal,
        or None if no model is available yet.
    """
    model = _load_model(str(model_path))
    if model is None:
        return None

    X = np.array([[
        reading.voltage_v,
        reading.current_a,
        reading.active_power_w,
        reading.power_factor,
    ]])

    # decision_function: higher = more normal (roughly -0.5 … +0.5)
    raw: float = float(model.decision_function(X)[0])

    # Map [-0.5, +0.5] → [0, 100] and clamp
    health = max(0.0, min(100.0, (raw + 0.5) * 100.0))
    return round(health, 1)


def get_health_score_for_profile(
    profile_id: uuid.UUID,
    reading: ReadingSample,
    db: Session,
) -> Optional[float]:
    """High-level helper: fit model if needed, then score a reading.

    Returns:
        Health score in [0, 100], or None if model cannot be built yet.
    """
    path = _model_path(profile_id)
    if not path.exists():
        # Try to fit on the fly (useful the first time the endpoint is called)
        fitted = fit_isolation_forest(profile_id, db)
        if not fitted:
            return None

    return score_reading(reading, path)


def model_exists(profile_id: uuid.UUID) -> bool:
    """Return True if a persisted model file exists for the given profile."""
    return _model_path(profile_id).exists()

