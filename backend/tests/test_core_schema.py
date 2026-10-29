"""Database constraint tests for the Phase 2 core schema.

These tests prove PostgreSQL rejects invalid rows even when the ORM is
bypassed by a future ingestion path or a manual SQL statement.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AuditLog,
    Channel,
    Command,
    Device,
    Event,
    Load,
    Schedule,
    Telemetry,
    User,
)

FAKE_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZmFrZWhhc2g"
NOW = datetime.now(timezone.utc)


def make_user(email: str = "owner@example.com") -> User:
    return User(email=email, password_hash=FAKE_ARGON2)


def make_device(owner: User, device_id: str = "PANEL-0001") -> Device:
    return Device(device_id=device_id, name="Test panel", owner_id=owner.id)


def make_channel(device: Device, ch: int = 1, **overrides) -> Channel:
    data = {"device_pk": device.id, "ch": ch, "name": f"Channel {ch}"}
    data.update(overrides)
    return Channel(**data)


def make_telemetry(device: Device, **overrides) -> Telemetry:
    data = {
        "device_pk": device.id,
        "ch": 1,
        "ts": NOW,
        "v": Decimal("230.00"),
        "i": Decimal("1.000"),
        "p": Decimal("230.00"),
        "e_kwh": Decimal("0.000"),
        "pf": Decimal("0.900"),
        "f": Decimal("50.00"),
        "relay": False,
        "state": "OFF",
        "buffered": False,
    }
    data.update(overrides)
    return Telemetry(**data)


def make_event(device: Device, **overrides) -> Event:
    data = {
        "id": uuid.uuid4(),
        "device_pk": device.id,
        "ch": 1,
        "ts": NOW,
        "type": "TEST_EVENT",
        "severity": "info",
        "message": "test",
    }
    data.update(overrides)
    return Event(**data)


def make_command(device: Device, **overrides) -> Command:
    data = {
        "cmd_id": uuid.uuid4(),
        "device_pk": device.id,
        "ch": 1,
        "action": "ON",
        "source": "user",
        "expires_at": NOW + timedelta(seconds=30),
    }
    data.update(overrides)
    return Command(**data)


def make_schedule(owner: User, device: Device, **overrides) -> Schedule:
    data = {
        "owner_id": owner.id,
        "device_pk": device.id,
        "ch": 1,
        "name": "Morning",
        "days_of_week": 1,
        "on_time": time(9, 0),
        "off_time": time(10, 0),
        "timezone": "Asia/Kolkata",
    }
    data.update(overrides)
    return Schedule(**data)


@pytest.fixture()
def owner_device(db_session):
    owner = make_user()
    db_session.add(owner)
    db_session.flush()
    device = make_device(owner)
    db_session.add(device)
    db_session.flush()
    return owner, device


def test_device_id_format_is_enforced(db_session, owner_device) -> None:
    owner, _ = owner_device
    db_session.add(make_device(owner, device_id="panel-1"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_device_id_is_rejected(db_session, owner_device) -> None:
    owner, device = owner_device
    db_session.add(device)
    db_session.commit()

    db_session.add(make_device(owner, device_id=device.device_id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_channel_number_must_be_one_or_two(db_session, owner_device) -> None:
    _, device = owner_device
    db_session.add(make_channel(device, ch=3))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_channel_is_unique_per_device(db_session, owner_device) -> None:
    _, device = owner_device
    db_session.add(make_channel(device, ch=1))
    db_session.commit()

    db_session.add(make_channel(device, ch=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_voltage_min_must_be_below_max(db_session, owner_device) -> None:
    _, device = owner_device
    db_session.add(
        make_channel(
            device,
            limit_voltage_min_v=Decimal("250.00"),
            limit_voltage_max_v=Decimal("200.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_load_code_format_and_category(db_session) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()

    db_session.add(
        Load(
            load_code="BAD-1",
            owner_id=owner.id,
            name="Bad",
            category="motor",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_telemetry_rejects_invalid_power_factor(
    db_session, owner_device
) -> None:
    _, device = owner_device
    db_session.add(make_telemetry(device, pf=Decimal("1.500")))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_telemetry_rejects_duplicate_primary_key(
    db_session, owner_device
) -> None:
    _, device = owner_device
    db_session.add(make_telemetry(device))
    db_session.commit()

    db_session.add(make_telemetry(device))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_telemetry_rejects_missing_device(db_session) -> None:
    orphan = Device(
        id=uuid.uuid4(),
        device_id="PANEL-9999",
        name="Orphan",
        owner_id=uuid.uuid4(),
    )
    db_session.add(make_telemetry(orphan))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_event_severity_is_validated(db_session, owner_device) -> None:
    _, device = owner_device
    db_session.add(make_event(device, severity="emergency"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_command_invariants(db_session, owner_device) -> None:
    _, device = owner_device

    db_session.add(make_command(device, status="PENDING", acked_at=NOW))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        make_command(
            device,
            issued_at=NOW,
            expires_at=NOW - timedelta(seconds=1),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_schedule_weekday_mask_and_times(db_session, owner_device) -> None:
    owner, device = owner_device

    db_session.add(make_schedule(owner, device, days_of_week=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        make_schedule(
            owner,
            device,
            on_time=time(9, 0),
            off_time=time(9, 0),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_device_cascades_owned_rows(
    db_session, owner_device
) -> None:
    owner, device = owner_device
    db_session.add_all(
        [
            make_channel(device, ch=1),
            make_telemetry(device),
            make_event(device),
            make_command(device),
            make_schedule(owner, device),
        ]
    )
    db_session.commit()

    db_session.execute(
        text("DELETE FROM devices WHERE id = :id"), {"id": device.id}
    )
    db_session.commit()

    for model in (Channel, Telemetry, Event, Command, Schedule):
        count = db_session.execute(select(func.count()).select_from(model)).scalar()
        assert count == 0, model.__name__


def test_user_with_device_cannot_be_deleted(db_session, owner_device) -> None:
    owner, _ = owner_device
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM users WHERE id = :id"), {"id": owner.id}
        )
        db_session.commit()
    db_session.rollback()


def test_check_constraint_names_are_not_double_prefixed(engine) -> None:
    with engine.connect() as conn:
        names = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname LIKE 'ck_%_ck_%'"
            )
        ).scalars().all()

    assert names == []


def test_audit_log_uses_an_identity_column(db_session) -> None:
    db_session.add(
        AuditLog(action="TEST", entity_type="test", entity_id="1")
    )
    db_session.commit()

    rows = db_session.execute(select(AuditLog)).scalars().all()
    assert len(rows) == 1
    assert rows[0].id >= 1
