"""Tests for Workstream 5: Automatic Live Telemetry, Event, and Heartbeat Pipeline.

Verifies:
- Live telemetry ingestion with backend calculation of apparent (S) and reactive (Q) power
- Buffered data handling (persisted to hypertable, but bypasses live recognition/anomaly checks)
- Quarantine of malformed or physically implausible packets
- Heartbeat ingestion and health tracking
- LWT and 15-second inactivity timeout offline detection
- Hardware event ingestion and deduplication
- Advisory anomaly event generation on live unbuffered stream
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Channel, Device, Event, Telemetry, User
from app.models.load_profile import LoadProfile, ProfileFingerprint
from app.security import hash_password
from app.services.live_pipeline import (
    check_offline_devices,
    compute_powers,
    ingest_event_packet,
    ingest_heartbeat_packet,
    ingest_status_packet,
    ingest_telemetry_packet,
    validate_telemetry_reading,
)

PASSWORD_HASH = hash_password("CorrectHorseBattery1")


def setup_user_and_device(db, device_id: str = "PANEL-0001") -> tuple[User, Device]:
    owner = User(
        email=f"owner_{device_id.lower()}@example.com",
        password_hash=PASSWORD_HASH,
        role="operator",
        is_active=True,
    )
    db.add(owner)
    db.flush()

    device = Device(
        device_id=device_id,
        name=f"Test Panel {device_id}",
        owner_id=owner.id,
        online=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(device)
    db.flush()

    ch1 = Channel(device_pk=device.id, ch=1, name="Channel 1", relay_commanded=False, state="OFF")
    ch2 = Channel(device_pk=device.id, ch=2, name="Channel 2", relay_commanded=False, state="OFF")
    db.add_all([ch1, ch2])
    db.commit()
    return owner, device


def test_compute_powers() -> None:
    # Resistive load: 230V, 4A, 920W, PF=1.0 -> S=920VA, Q=0VAr
    s, q = compute_powers(230.0, 4.0, 920.0)
    assert s == 920.0
    assert q == 0.0

    # Inductive load: 230V, 5A, 800W -> S=1150VA, Q=sqrt(1150^2 - 800^2) = 826.14 VAr
    s, q = compute_powers(230.0, 5.0, 800.0)
    assert s == 1150.0
    assert q == 826.14


def test_telemetry_ingestion_with_computed_powers(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0010")

    broadcast_messages = []

    def fake_broadcast(dev_id: str, msg: dict) -> None:
        broadcast_messages.append((dev_id, msg))

    now_ts = datetime.now(timezone.utc).timestamp()
    reading = {
        "schema": 1,
        "ts": now_ts,
        "v": 230.0,
        "i": 4.0,
        "p": 920.0,
        "pf": 0.99,
        "f": 50.0,
        "e_kwh": 5.432,
        "relay": True,
        "state": "RUNNING",
        "buffered": False,
        "clock_synced": True,
    }

    success, telem, err = ingest_telemetry_packet(
        db_session,
        device.device_id,
        ch=1,
        data=reading,
        broadcast_fn=fake_broadcast,
    )
    assert success is True
    assert err is None
    assert telem is not None
    assert float(telem.v) == 230.0
    assert float(telem.i) == 4.0
    assert float(telem.p) == 920.0
    assert telem.relay is True
    assert telem.state == "RUNNING"
    assert telem.buffered is False

    # Verify channel was updated
    ch1 = db_session.scalar(
        select(Channel).where(Channel.device_pk == device.id, Channel.ch == 1)
    )
    assert ch1.relay_commanded is True
    assert ch1.state == "RUNNING"
    assert ch1.last_telemetry_at is not None

    # Verify broadcast received calculated S and Q
    assert len(broadcast_messages) == 1
    dev_id, payload = broadcast_messages[0]
    assert dev_id == device.device_id
    assert payload["s"] == 920.0
    assert payload["q"] == 0.0


def test_buffered_telemetry_packet_skips_live_anomaly(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0020")

    # Ingest buffered packet with high current
    past_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
    reading = {
        "schema": 1,
        "ts": past_ts,
        "v": 230.0,
        "i": 35.0,  # high current
        "p": 8000.0,
        "pf": 0.95,
        "f": 50.0,
        "e_kwh": 10.0,
        "relay": True,
        "state": "RUNNING",
        "buffered": True,  # buffered flag
    }

    success, telem, err = ingest_telemetry_packet(
        db_session,
        device.device_id,
        ch=1,
        data=reading,
    )
    assert success is True
    assert telem is not None
    assert telem.buffered is True

    # No anomaly events should be created for buffered data
    events = list(
        db_session.scalars(
            select(Event).where(Event.device_pk == device.id)
        ).all()
    )
    assert len(events) == 0


def test_malformed_telemetry_quarantined_not_stored(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0030")

    # 1. Voltage too high (400V)
    bad_v = {
        "ts": datetime.now(timezone.utc).timestamp(),
        "v": 400.0,
        "i": 2.0,
        "p": 460.0,
        "pf": 0.99,
        "f": 50.0,
        "e_kwh": 1.0,
        "relay": True,
        "state": "RUNNING",
    }
    ok, _, err = ingest_telemetry_packet(db_session, device.device_id, ch=1, data=bad_v)
    assert ok is False
    assert "Voltage" in err

    # 2. Negative power
    bad_p = {
        "ts": datetime.now(timezone.utc).timestamp(),
        "v": 230.0,
        "i": 2.0,
        "p": -10.0,
        "pf": 0.99,
        "f": 50.0,
        "e_kwh": 1.0,
        "relay": True,
        "state": "RUNNING",
    }
    ok, _, err = ingest_telemetry_packet(db_session, device.device_id, ch=1, data=bad_p)
    assert ok is False
    assert "Active power" in err

    # 3. Missing fields
    incomplete = {"v": 230.0}
    ok, _, err = ingest_telemetry_packet(db_session, device.device_id, ch=1, data=incomplete)
    assert ok is False
    assert "Missing required telemetry field" in err

    # Ensure no rows entered telemetry table
    count = len(
        list(db_session.scalars(select(Telemetry).where(Telemetry.device_pk == device.id)).all())
    )
    assert count == 0


def test_heartbeat_updates_device_health(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0040")

    heartbeat_data = {
        "uptime_s": 3600,
        "free_heap": 210000,
        "rssi": -55,
        "channels": [
            {"ch": 1, "relay": True, "state": "RUNNING"},
            {"ch": 2, "relay": False, "state": "OFF"},
        ],
    }
    ingest_heartbeat_packet(db_session, device.device_id, heartbeat_data)

    db_session.refresh(device)
    assert device.online is True
    assert device.last_status == heartbeat_data
    assert device.last_seen_at is not None


def test_status_lwt_marks_device_offline(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0050")
    assert device.online is True

    lwt_data = {
        "schema": 1,
        "ts": 0,
        "online": False,
        "device_id": device.device_id,
        "reason": "lwt",
    }
    ingest_status_packet(db_session, device.device_id, lwt_data)

    db_session.refresh(device)
    assert device.online is False

    # Verify disconnect event recorded
    event = db_session.scalar(
        select(Event).where(Event.device_pk == device.id, Event.type == "DEVICE_OFFLINE")
    )
    assert event is not None
    assert event.severity == "warning"
    assert "offline" in event.message.lower()


def test_fifteen_second_timeout_marks_device_offline(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0060")
    device.online = True
    device.last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=25)
    db_session.commit()

    timed_out = check_offline_devices(db_session, timeout_seconds=15)
    assert len(timed_out) >= 1
    assert any(d.device_id == device.device_id for d in timed_out)

    db_session.refresh(device)
    assert device.online is False

    event = db_session.scalar(
        select(Event).where(Event.device_pk == device.id, Event.type == "DEVICE_OFFLINE")
    )
    assert event is not None
    assert "timed out after 15s" in event.message


def test_event_ingestion_and_deduplication(db_session) -> None:
    _, device = setup_user_and_device(db_session, "PANEL-0070")

    event_id = str(uuid.uuid4())
    event_payload = {
        "schema": 1,
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).timestamp(),
        "type": "PROTECTION_TRIP",
        "severity": "critical",
        "ch": 1,
        "message": "Overcurrent trip: 10.2 A exceeded 8.0 A limit",
        "data": {"rule": "OVERCURRENT", "measured": 10.2, "limit": 8.0},
    }

    # 1. Ingest event
    ok, ev, err = ingest_event_packet(db_session, device.device_id, event_payload)
    assert ok is True
    assert ev is not None
    assert str(ev.id) == event_id
    assert ev.type == "PROTECTION_TRIP"
    assert ev.severity == "critical"
    assert ev.ch == 1

    # 2. Duplicate ingestion must succeed idempotently without creating a second row
    ok2, ev2, err2 = ingest_event_packet(db_session, device.device_id, event_payload)
    assert ok2 is True
    assert str(ev2.id) == event_id

    total_events = list(
        db_session.scalars(select(Event).where(Event.device_pk == device.id)).all()
    )
    assert len(total_events) == 1


def test_live_reading_with_anomaly_creates_warning_event(db_session) -> None:
    owner, device = setup_user_and_device(db_session, "PANEL-0080")

    # Create a confirmed load profile with baseline fingerprint (e.g. 2.0 A, 460 W)
    profile = LoadProfile(
        owner_id=owner.id,
        display_name="Air Conditioner",
        user_confirmed=True,
        channel_last_seen=1,
        nominal_current_a=Decimal("2.000"),
        nominal_power_w=Decimal("460.00"),
    )
    db_session.add(profile)
    db_session.flush()

    fp = ProfileFingerprint(
        profile_id=profile.id,
        voltage_mean=230.0,
        voltage_std=1.0,
        current_mean=2.0,
        current_std=0.1,
        current_min=1.8,
        current_max=2.2,
        active_power_mean=460.0,
        active_power_std=10.0,
        active_power_min=440.0,
        active_power_max=480.0,
        power_factor_mean=0.95,
        power_factor_std=0.02,
        frequency_mean=50.0,
        frequency_std=0.1,
        apparent_power_s=460.0,
        reactive_power_q=100.0,
        reactive_ratio_q_s=0.217,
        cv_power=0.021,
        power_per_volt_sq=0.0087,
    )
    db_session.add(fp)
    db_session.commit()

    # Ingest a live unbuffered reading with anomalous high current (8.0 A, Z > 40)
    anomalous_reading = {
        "schema": 1,
        "ts": datetime.now(timezone.utc).timestamp(),
        "v": 230.0,
        "i": 8.0,
        "p": 1800.0,
        "pf": 0.95,
        "f": 50.0,
        "e_kwh": 2.5,
        "relay": True,
        "state": "RUNNING",
        "buffered": False,
    }

    ok, telem, err = ingest_telemetry_packet(
        db_session,
        device.device_id,
        ch=1,
        data=anomalous_reading,
    )
    assert ok is True

    # Verify warning anomaly event was generated
    events = list(
        db_session.scalars(
            select(Event).where(
                Event.device_pk == device.id,
                Event.ch == 1,
            )
        ).all()
    )
    assert len(events) >= 1
    anomaly_event = events[0]
    assert anomaly_event.severity in ("warning", "critical")
    assert "anomaly" in anomaly_event.type.lower() or "deviation" in anomaly_event.type.lower()

    # Rule 5: relay must NOT be changed autonomously by AI!
    ch1 = db_session.scalar(
        select(Channel).where(Channel.device_pk == device.id, Channel.ch == 1)
    )
    assert ch1.relay_commanded is True


def test_websocket_live_connection(db_session) -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    _, device = setup_user_and_device(db_session, "PANEL-0090")

    with TestClient(app) as test_client:
        with test_client.websocket_connect(f"/ws/live/{device.device_id}") as ws:
            ws.send_text("ping")
            pong = ws.receive_text()
            assert pong == "pong"
