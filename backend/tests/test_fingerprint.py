"""Unit tests for the fingerprint extraction engine."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from app.services.fingerprint import (
    ExtractedFingerprint,
    ReadingSample,
    extract_fingerprint,
)


def test_insufficient_samples_raises_error():
    samples = [ReadingSample(230.0, 0.5, 100.0, 0.85, 50.0) for _ in range(5)]
    with pytest.raises(ValueError, match="Insufficient samples"):
        extract_fingerprint(samples)


def test_synthetic_motor_fingerprint_characteristics():
    # Simulate a steady inductive motor (~125 W, PF ~0.65)
    samples = []
    # 2 early surge samples
    samples.append(ReadingSample(230.0, 1.60, 180.0, 0.50, 50.0))
    samples.append(ReadingSample(230.0, 1.40, 160.0, 0.55, 50.0))
    # 18 steady running samples
    for _ in range(18):
        samples.append(ReadingSample(230.0, 0.95, 125.0, 0.68, 50.0))

    fp = extract_fingerprint(samples)

    assert fp.sample_count == 20
    assert fp.voltage_mean == 230.0
    assert 0.90 <= fp.current_mean <= 1.10
    assert 120.0 <= fp.active_power_mean <= 140.0
    assert 0.60 <= fp.power_factor_mean <= 0.75
    # Inductive load has high reactive power and Q/S ratio
    assert fp.apparent_power_s > fp.active_power_mean
    assert fp.reactive_power_q > 100.0
    assert fp.reactive_ratio_q_s > 0.50
    # Startup ratio detected (> 1.2)
    assert fp.startup_ratio is not None
    assert fp.startup_ratio >= 1.30


def test_synthetic_bulb_fingerprint_characteristics():
    # Simulate a steady resistive bulb array (~200 W, PF = 1.0)
    samples = [ReadingSample(230.0, 0.87, 200.0, 1.0, 50.0) for _ in range(25)]

    fp = extract_fingerprint(samples)

    assert fp.sample_count == 25
    assert fp.voltage_mean == 230.0
    assert fp.current_mean == 0.87
    assert fp.active_power_mean == 200.0
    assert fp.power_factor_mean == 1.0
    # Resistive load: Apparent power ≈ Active power, Reactive power is tiny
    assert abs(fp.apparent_power_s - fp.active_power_mean) < 1.0
    assert fp.reactive_power_q < 10.0
    assert fp.reactive_ratio_q_s < 0.05
    assert fp.cv_power == 0.0  # Perfectly steady


def test_fingerprint_on_cleaned_historical_csv():
    csv_path = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "cleaned"
        / "cleaned_pzem_training_data_20261015_160424.csv"
    )

    assert csv_path.exists(), "Cleaned CSV must exist"

    samples = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append(
                ReadingSample(
                    voltage_v=float(row["voltage_V"]),
                    current_a=float(row["current_A"]),
                    active_power_w=float(row["active_power_W"]),
                    power_factor=float(row["power_factor_pzem"]),
                    frequency_hz=float(row["frequency_Hz"]),
                )
            )

    fp = extract_fingerprint(samples)

    assert fp.sample_count == 87
    assert 225.0 <= fp.voltage_mean <= 228.0
    assert 0.50 <= fp.current_mean <= 0.70
    assert fp.power_factor_mean < 0.70  # Confirms inductive load
    assert fp.reactive_ratio_q_s > 0.50
