"""Command dispatch, execution tracking, and acknowledgement processing service.

Schema reference: docs/mqtt_contract.md §8-9 and docs/database_schema.md §4.9.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import paho.mqtt.publish as publish
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Channel, Command, Device, User
from app.schemas.command import CommandAckIn, CommandCreate

logger = logging.getLogger(__name__)


def normalize_channel_state(st: str | None) -> str:
    if not st:
        return "OFF"
    mapping = {
        "INRUSH": "STARTING",
        "FAULT_RETRY": "RETRY_WAIT",
        "LOCKOUT": "LOCKED_OUT",
        "METER_LOST": "METER_FAULT",
    }
    mapped = mapping.get(st.upper(), st.upper())
    allowed = {"OFF", "STARTING", "RUNNING", "TRIPPED", "RETRY_WAIT", "LOCKED_OUT", "METER_FAULT"}
    return mapped if mapped in allowed else "OFF"


def default_mqtt_publisher(topic: str, payload_str: str, hostname: str, port: int) -> bool:
    """Default publisher using paho.mqtt.publish.single."""
    try:
        publish.single(
            topic=topic,
            payload=payload_str,
            qos=1,
            retain=False,
            hostname=hostname,
            port=port,
        )
        return True
    except Exception as exc:  # pragma: no cover - network/broker error
        logger.error("Failed to publish command to MQTT topic %s: %s", topic, exc)
        return False


def issue_command(
    db: Session,
    device: Device,
    user: User,
    payload: CommandCreate,
    settings: Settings,
    mqtt_publisher: Optional[Callable[[str, str, str, int], bool]] = None,
) -> Command:
    """Validate, persist, and dispatch a relay command to MQTT."""
    # Ensure channel exists on device
    channel = db.scalar(
        select(Channel).where(
            Channel.device_pk == device.id,
            Channel.ch == payload.ch,
        )
    )
    if channel is None:
        raise ValueError(f"Channel {payload.ch} does not exist on device {device.device_id}")

    now = datetime.now(timezone.utc)
    cmd_lifetime = 10  # default 10 seconds per contract §8.2
    expires_at = now + timedelta(seconds=cmd_lifetime)

    cmd = Command(
        cmd_id=uuid.uuid4(),
        device_pk=device.id,
        ch=payload.ch,
        action=payload.action,
        source=payload.source,
        priority=payload.priority,
        duration_seconds=payload.duration_seconds,
        requested_by=user.id,
        status="PENDING",
        issued_at=now,
        expires_at=expires_at,
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)

    # Prepare MQTT payload matching contract §8
    mqtt_payload = {
        "schema": 1,
        "cmd_id": str(cmd.cmd_id),
        "ch": cmd.ch,
        "action": cmd.action,
        "priority": cmd.priority,
        "issued_at": int(cmd.issued_at.timestamp()),
        "expires_at": int(cmd.expires_at.timestamp()),
        "source": cmd.source,
    }
    if cmd.duration_seconds is not None:
        mqtt_payload["duration_seconds"] = cmd.duration_seconds

    payload_json = json.dumps(mqtt_payload)
    topic = f"panel/{device.device_id}/cmd"

    publisher = mqtt_publisher or default_mqtt_publisher
    success = publisher(topic, payload_json, settings.mqtt_host, settings.mqtt_port)

    if success:
        cmd.status = "SENT"
    else:
        cmd.status = "FAILED"
        cmd.reason = "MQTT_PUBLISH_FAILED"

    db.commit()
    db.refresh(cmd)
    return cmd


def handle_command_ack(db: Session, ack: CommandAckIn) -> Optional[Command]:
    """Process an acknowledgement payload from panel/{DEVICE_ID}/ack."""
    cmd = db.scalar(select(Command).where(Command.cmd_id == ack.cmd_id))
    if cmd is None:
        logger.warning("Received ack for unknown command_id %s", ack.cmd_id)
        return None

    now = datetime.now(timezone.utc)
    cmd.acked_at = now
    cmd.relay_after = ack.relay
    cmd.state_after = ack.state
    cmd.reason = ack.reason

    if ack.result == "DONE":
        cmd.status = "DONE"
        if ack.ts is not None:
            cmd.executed_at = datetime.fromtimestamp(ack.ts, tz=timezone.utc)
        else:
            cmd.executed_at = now

        # Update the live channel row
        channel = db.scalar(
            select(Channel).where(
                Channel.device_pk == cmd.device_pk,
                Channel.ch == cmd.ch,
            )
        )
        if channel:
            channel.relay_commanded = ack.relay
            if ack.state:
                channel.state = normalize_channel_state(ack.state)
            channel.updated_at = now

    elif ack.result in ("REJECTED", "REFUSED"):
        cmd.status = "REJECTED"
    else:
        cmd.status = "FAILED"

    db.commit()
    db.refresh(cmd)
    return cmd


def check_command_timeouts(db: Session) -> int:
    """Find expired pending or sent commands and transition them to TIMED_OUT."""
    now = datetime.now(timezone.utc)
    expired_cmds = list(
        db.scalars(
            select(Command).where(
                Command.status.in_(("PENDING", "SENT")),
                Command.expires_at <= now,
            )
        ).all()
    )

    for cmd in expired_cmds:
        cmd.status = "TIMED_OUT"
        cmd.reason = "TIMEOUT_NO_ACK"

    if expired_cmds:
        db.commit()

    return len(expired_cmds)
