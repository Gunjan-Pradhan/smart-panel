"""Real-Time Anomaly Detection Engine.

Implements Section 3.5 of the build specification:
- Rolling Z-score anomaly detection across V, I, P, PF against learned profile fingerprints
- Noise floor protection to avoid false spikes on tightly regulated baselines
- Transient inrush filtering (DOL motor startup suppression for <= 2.0 seconds)
- Isolation Forest multivariate anomaly scoring
- PostgreSQL event logging for warning and critical deviations
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.load_profile import LoadProfile, ProfileFingerprint
from app.services.fingerprint import ReadingSample

# Noise floors to prevent division by zero or hypersensitivity on clean loads
VOLTAGE_STD_FLOOR = 2.0     # Volts
CURRENT_STD_FLOOR = 0.05    # Amperes
POWER_STD_FLOOR = 5.0       # Watts
PF_STD_FLOOR = 0.03         # Dimensionless

# Z-score thresholds
Z_WARNING_THRESHOLD = 2.5
Z_CRITICAL_THRESHOLD = 4.0


@dataclass(frozen=True)
class ZScores:
    z_voltage: float
    z_current: float
    z_power: float
    z_power_factor: float
    max_z: float


@dataclass(frozen=True)
class AnomalyEvaluation:
    is_anomaly: bool
    severity: str  # "info", "warning", "critical"
    flags: list[str]
    is_transient_inrush: bool
    z_scores: ZScores
    isolation_score: float | None
    message: str
    details: dict[str, Any]


def calculate_z_scores(
    sample: ReadingSample,
    fp: ProfileFingerprint,
) -> tuple[ZScores, list[str]]:
    """Calculates Z-scores for each parameter with variance floor protection."""
    v_sigma = max(fp.voltage_std, VOLTAGE_STD_FLOOR)
    i_sigma = max(fp.current_std, CURRENT_STD_FLOOR)
    p_sigma = max(fp.active_power_std, POWER_STD_FLOOR)
    pf_sigma = max(fp.power_factor_std, PF_STD_FLOOR)

    zv = abs(sample.voltage_v - fp.voltage_mean) / v_sigma
    zi = abs(sample.current_a - fp.current_mean) / i_sigma
    zp = abs(sample.active_power_w - fp.active_power_mean) / p_sigma
    zpf = abs(sample.power_factor - fp.power_factor_mean) / pf_sigma

    max_z = max(zv, zi, zp, zpf)

    flags: list[str] = []
    # Identify specific anomalies
    if zi >= Z_WARNING_THRESHOLD:
        flags.append("overcurrent" if sample.current_a > fp.current_mean else "undercurrent")
    if zp >= Z_WARNING_THRESHOLD:
        flags.append("overpower" if sample.active_power_w > fp.active_power_mean else "underpower")
    if zv >= Z_WARNING_THRESHOLD:
        flags.append("voltage_swell" if sample.voltage_v > fp.voltage_mean else "voltage_sag")
    if zpf >= Z_WARNING_THRESHOLD or sample.power_factor < 0.50:
        flags.append("poor_power_factor")

    z_obj = ZScores(
        z_voltage=round(zv, 2),
        z_current=round(zi, 2),
        z_power=round(zp, 2),
        z_power_factor=round(zpf, 2),
        max_z=round(max_z, 2),
    )
    return z_obj, flags


class IsolationForestScorer:
    """Multi-variate anomaly detector utilizing Scikit-Learn Isolation Forest."""

    def __init__(self, contamination: float = 0.05, random_state: int = 42) -> None:
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=100,
        )
        self.is_fitted = False

    def fit(self, baseline_samples: Sequence[ReadingSample]) -> None:
        if len(baseline_samples) < 15:
            return
        X = np.array([
            [s.voltage_v, s.current_a, s.active_power_w, s.power_factor]
            for s in baseline_samples
        ])
        self.model.fit(X)
        self.is_fitted = True

    def score(self, sample: ReadingSample) -> float | None:
        if not self.is_fitted:
            return None
        X = np.array([[sample.voltage_v, sample.current_a, sample.active_power_w, sample.power_factor]])
        # decision_function returns negative values for anomalies, positive for inliers
        score = float(self.model.decision_function(X)[0])
        return round(score, 3)


class AnomalyDetector:
    """Service for evaluating readings against profile baselines and logging alerts."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def evaluate_sample(
        self,
        sample: ReadingSample,
        fp: ProfileFingerprint,
        is_startup_window: bool = False,
        iso_scorer: IsolationForestScorer | None = None,
    ) -> AnomalyEvaluation:
        """Evaluates a single reading sample against a target fingerprint."""
        z_obj, flags = calculate_z_scores(sample, fp)

        # Baseline severity based on max Z
        if z_obj.max_z >= Z_CRITICAL_THRESHOLD:
            severity = "critical"
        elif z_obj.max_z >= Z_WARNING_THRESHOLD:
            severity = "warning"
        else:
            severity = "info"

        is_anomaly = severity in ("warning", "critical")
        is_transient_inrush = False

        # Inrush suppression check
        # If in startup window and deviation is overcurrent/overpower, suppress warning/critical
        if is_startup_window and is_anomaly:
            non_inrush_flags = [f for f in flags if f not in ("overcurrent", "overpower")]
            if not non_inrush_flags:
                is_transient_inrush = True
                severity = "info"
                is_anomaly = False

        # Multivariate Isolation Forest score
        iso_score = iso_scorer.score(sample) if iso_scorer else None

        # Build human-readable explanation
        if is_transient_inrush:
            message = (
                f"Transient inrush detected during motor startup (Current: {sample.current_a:.2f}A, "
                f"Z={z_obj.z_current}). Alarm suppressed."
            )
        elif is_anomaly:
            flag_str = ", ".join(flags)
            message = (
                f"Electrical anomaly detected [{flag_str}] with max Z={z_obj.max_z:.2f} "
                f"(Current: {sample.current_a:.2f}A, Power: {sample.active_power_w:.1f}W)."
            )
        else:
            message = "Operating within normal nominal thresholds."

        details = {
            "sample": {
                "voltage": sample.voltage_v,
                "current": sample.current_a,
                "power": sample.active_power_w,
                "power_factor": sample.power_factor,
            },
            "baseline": {
                "voltage_mean": fp.voltage_mean,
                "current_mean": fp.current_mean,
                "power_mean": fp.active_power_mean,
                "pf_mean": fp.power_factor_mean,
            },
        }

        return AnomalyEvaluation(
            is_anomaly=is_anomaly,
            severity=severity,
            flags=flags,
            is_transient_inrush=is_transient_inrush,
            z_scores=z_obj,
            isolation_score=iso_score,
            message=message,
            details=details,
        )

    def record_anomaly_event(
        self,
        device_pk: uuid.UUID,
        channel: int,
        evaluation: AnomalyEvaluation,
    ) -> Event | None:
        """Persists an anomaly event in the events table if warning or critical."""
        if not self.db or evaluation.severity not in ("warning", "critical"):
            return None

        event_type = f"anomaly_{evaluation.flags[0]}" if evaluation.flags else "anomaly_deviation"
        event = Event(
            id=uuid.uuid4(),
            device_pk=device_pk,
            ch=channel,
            ts=datetime.now(timezone.utc),
            type=event_type,
            severity=evaluation.severity,
            message=evaluation.message,
            data={
                "flags": evaluation.flags,
                "z_scores": {
                    "voltage": evaluation.z_scores.z_voltage,
                    "current": evaluation.z_scores.z_current,
                    "power": evaluation.z_scores.z_power,
                    "pf": evaluation.z_scores.z_power_factor,
                    "max_z": evaluation.z_scores.max_z,
                },
                "isolation_score": evaluation.isolation_score,
                "details": evaluation.details,
            },
            received_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_recent_anomaly_events(
        self,
        device_pk: uuid.UUID,
        channel: int | None = None,
        limit: int = 20,
    ) -> list[Event]:
        """Queries recent anomaly events recorded for a device."""
        if not self.db:
            return []

        stmt = (
            select(Event)
            .where(
                Event.device_pk == device_pk,
                Event.type.startswith("anomaly_"),
            )
        )
        if channel is not None:
            stmt = stmt.where(Event.ch == channel)

        stmt = stmt.order_by(desc(Event.ts)).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

