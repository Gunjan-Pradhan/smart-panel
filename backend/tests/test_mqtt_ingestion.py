"""Tests for MQTT telemetry parsing, validation, database ingestion, and simulator isolation."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.channel import Channel
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.services.ingestion import TelemetryIngestionService
from app.services.mqtt_adapter import MQTTTelemetryAdapter
from simulator.telemetry_simulator import SafeTelemetrySimulator

FAKE_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZmFrZWhhc2g"


def test_mqtt_topic_parsing():
    adapter = MQTTTelemetryAdapter()

    # Topic parsing
    r1 = adapter.parse_topic("energy/dual_pzem/circuit1/voltage_V", "230.4")
    assert r1 is not None
    assert r1.channel == 1
    assert r1.metric_name == "voltage_V"
    assert r1.value == 230.4

    r2 = adapter.parse_topic("energy/dual_pzem/circuit2/relay/state", "ON")
    assert r2 is not None
    assert r2.channel == 2
    assert r2.value is True

    # Unrelated topic
    r3 = adapter.parse_topic("home/kitchen/light", "ON")
    assert r3 is None


def test_data_validation_accepts_valid_and_rejects_corrupt_readings():
    adapter = MQTTTelemetryAdapter()

    # Valid motor reading
    valid, err = adapter.validate_metrics(v=230.5, i=0.95, p=125.0, pf=0.68, f=50.0)
    assert valid is True
    assert err is None

    # Corrupt UART framing glitches (like seen in CSV 1 and CSV 2):
    # 1. 500,000 Amps
    v1, e1 = adapter.validate_metrics(v=230.0, i=590680.0, p=100.0, pf=0.9, f=50.0)
    assert v1 is False
    assert "Current exceeds plausible maximum" in e1

    # 2. 4,700 Volts
    v2, e2 = adapter.validate_metrics(v=4740.0, i=0.5, p=100.0, pf=0.9, f=50.0)
    assert v2 is False
    assert "Voltage out of plausible bounds" in e2

    # 3. Impossible Power Factor (> 1.0)
    v3, e3 = adapter.validate_metrics(v=230.0, i=1.0, p=100.0, pf=243.0, f=50.0)
    assert v3 is False
    assert "Power factor outside [0.0, 1.0]" in e3

    # 4. Non-finite values (NaN / Inf)
    v4, e4 = adapter.validate_metrics(v=float("nan"), i=1.0, p=100.0, pf=0.9, f=50.0)
    assert v4 is False
    assert "Non-finite value" in e4


def test_safe_simulator_generates_distinct_profiles():
    sim = SafeTelemetrySimulator(seed=123)

    # 1. Motor has inductive PF (~0.68) and reactive power Q
    motor_frame = sim.generate_motor_frame(time_elapsed_s=5.0)
    assert motor_frame.channel == 1
    assert 0.60 <= motor_frame.power_factor <= 0.75
    assert motor_frame.reactive_power_var > 100.0
    assert motor_frame.is_simulated is True

    # 2. Motor startup surge test
    surge_frame = sim.generate_motor_frame(time_elapsed_s=0.5)
    assert surge_frame.current_a > motor_frame.current_a  # Inrush current > steady current
    assert surge_frame.state == "STARTING"

    # 3. Bulb has near unity PF (~1.0) and negligible reactive power
    bulb_frame = sim.generate_bulb_frame(wattage=200.0)
    assert bulb_frame.channel == 2
    assert bulb_frame.power_factor >= 0.99
    assert bulb_frame.reactive_power_var < 15.0


def test_telemetry_ingestion_into_timescaledb(db_session):
    user = User(email="ingest_test@example.com", password_hash=FAKE_ARGON2)
    db_session.add(user)
    db_session.flush()

    device = Device(owner_id=user.id, device_id="PANEL-0001", name="Test Panel")
    db_session.add(device)
    db_session.flush()

    adapter = MQTTTelemetryAdapter()
    ingestion = TelemetryIngestionService(db_session)

    # Build and ingest valid simulated reading
    rec = adapter.build_record(
        channel=1,
        v=230.2,
        i=0.94,
        p=124.0,
        pf=0.68,
        f=50.0,
        is_simulated=True,
    )
    assert rec.validity == "simulated"

    entry = ingestion.ingest_record(rec, device_id="PANEL-0001")
    assert entry is not None
    assert entry.ch == 1
    assert float(entry.v) == 230.2
    assert float(entry.p) == 124.0

    # Query back from DB
    persisted = db_session.execute(
        select(Telemetry).where(Telemetry.device_pk == device.id)
    ).scalars().all()
    assert len(persisted) == 1

