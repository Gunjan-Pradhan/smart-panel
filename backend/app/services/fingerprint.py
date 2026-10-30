"""Fingerprint extraction engine for electrical loads.

Computes statistical and physical features from valid PZEM readings.
Adheres strictly to Section 3.3 of the build specification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

FEATURE_SET_VERSION = "1.0.0"
MIN_SAMPLES_FOR_FINGERPRINT = 10


@dataclass(frozen=True)
class ReadingSample:
    """A single valid electrical reading for feature calculation."""

    voltage_v: float
    current_a: float
    active_power_w: float
    power_factor: float
    frequency_hz: float
    timestamp_s: float | None = None


@dataclass(frozen=True)
class ExtractedFingerprint:
    """Statistical and physical fingerprint extracted from valid samples."""

    sample_count: int
    voltage_mean: float
    voltage_std: float
    current_mean: float
    current_std: float
    current_min: float
    current_max: float
    active_power_mean: float
    active_power_std: float
    active_power_min: float
    active_power_max: float
    power_factor_mean: float
    power_factor_std: float
    frequency_mean: float
    frequency_std: float
    apparent_power_s: float
    reactive_power_q: float
    reactive_ratio_q_s: float
    cv_power: float
    power_per_volt_sq: float
    startup_ratio: float | None
    transition_count: int
    feature_set_version: str = FEATURE_SET_VERSION


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: Sequence[float], mean_val: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((x - mean_val) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def extract_fingerprint(
    samples: Sequence[ReadingSample],
    feature_set_version: str = FEATURE_SET_VERSION,
) -> ExtractedFingerprint:
    """Extracts the complete electrical fingerprint from a sequence of valid readings.

    Raises:
        ValueError: If sample count is less than MIN_SAMPLES_FOR_FINGERPRINT.
    """
    n = len(samples)
    if n < MIN_SAMPLES_FOR_FINGERPRINT:
        raise ValueError(
            f"Insufficient samples: {n} provided, minimum {MIN_SAMPLES_FOR_FINGERPRINT} required."
        )

    voltages = [s.voltage_v for s in samples]
    currents = [s.current_a for s in samples]
    powers = [s.active_power_w for s in samples]
    pfs = [s.power_factor for s in samples]
    freqs = [s.frequency_hz for s in samples]

    # Means
    v_mean = _mean(voltages)
    i_mean = _mean(currents)
    p_mean = _mean(powers)
    pf_mean = _mean(pfs)
    f_mean = _mean(freqs)

    # Standard Deviations
    v_std = _std(voltages, v_mean)
    i_std = _std(currents, i_mean)
    p_std = _std(powers, p_mean)
    pf_std = _std(pfs, pf_mean)
    f_std = _std(freqs, f_mean)

    # Min / Max
    i_min = min(currents)
    i_max = max(currents)
    p_min = min(powers)
    p_max = max(powers)

    # Physical Apparent Power S and Reactive Power Q
    s = v_mean * i_mean
    # Clamp power to not exceed S for physical consistency
    p_bounded = min(p_mean, s)
    q = math.sqrt(max(0.0, s * s - p_bounded * p_bounded))
    q_s_ratio = q / s if s > 0.001 else 0.0

    # Coefficient of variation of active power (steadiness)
    cv_power = (p_std / p_mean) if p_mean > 0.001 else 0.0

    # Voltage-normalized power: P / V^2
    power_per_volt_sq = (p_mean / (v_mean ** 2)) if v_mean > 1.0 else 0.0

    # Startup ratio: peak current during the first 5 samples / steady-state current
    startup_ratio: float | None = None
    if n >= 15 and i_mean > 0.01:
        early_peak = max(currents[:5])
        steady_current = _mean(currents[5:])
        if steady_current > 0.01:
            startup_ratio = round(early_peak / steady_current, 3)

    # Transitions count: count significant power steps (> 25% change)
    transitions = 0
    for idx in range(1, n):
        prev_p = powers[idx - 1]
        curr_p = powers[idx]
        delta = abs(curr_p - prev_p)
        if delta > 15.0 and (prev_p == 0 or delta / max(prev_p, 10.0) > 0.25):
            transitions += 1

    return ExtractedFingerprint(
        sample_count=n,
        voltage_mean=round(v_mean, 2),
        voltage_std=round(v_std, 3),
        current_mean=round(i_mean, 4),
        current_std=round(i_std, 4),
        current_min=round(i_min, 4),
        current_max=round(i_max, 4),
        active_power_mean=round(p_mean, 2),
        active_power_std=round(p_std, 3),
        active_power_min=round(p_min, 2),
        active_power_max=round(p_max, 2),
        power_factor_mean=round(pf_mean, 3),
        power_factor_std=round(pf_std, 3),
        frequency_mean=round(f_mean, 2),
        frequency_std=round(f_std, 3),
        apparent_power_s=round(s, 2),
        reactive_power_q=round(q, 2),
        reactive_ratio_q_s=round(q_s_ratio, 3),
        cv_power=round(cv_power, 4),
        power_per_volt_sq=round(power_per_volt_sq, 6),
        startup_ratio=startup_ratio,
        transition_count=transitions,
        feature_set_version=feature_set_version,
    )

