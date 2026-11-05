"""Live MQTT telemetry, event, heartbeat, and status ingestion pipeline.

Adheres strictly to docs/mqtt_contract.md §5-9.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Optional, Tuple

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import Channel, Command, Device, Event, Telemetry
from app.models.load_profile import LoadProfile, ProfileFingerprint
from app.schemas.command import CommandAckIn
from app.services.anomaly_detector import AnomalyDetector
from app.services.command_service import handle_command_ack, normalize_channel_state
from app.services.fingerprint import ReadingSample

logger = logging.getLogger(__name__)

# Physical bounds for single-phase 230V AC per contract §5.1 & §15.1
MIN_PLAUSIBLE_VOLTAGE_V = 50.0
MAX_PLAUSIBLE_VOLTAGE_V = 300.0
MAX_PLAUSIBLE_CURRENT_A = 50.0
MIN_PLAUSIBLE_FREQ_HZ = 40.0
MAX_PLAUSIBLE_FREQ_HZ = 65.0


def validate_telemetry_reading(data: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate telemetry packet against docs/mqtt_contract.md physical bounds."""
    required = ("v", "i", "p", "pf", "f", "e_kwh", "relay", "state", "ts")
    for f in required:
        if f not in data:
            return False, f"Missing required telemetry field: {f}"

    try:
        v = float(data["v"])
        i = float(data["i"])
        p = float(data["p"])
        pf = float(data["pf"])
        f_val = float(data["f"])
        e_kwh = float(data["e_kwh"])
    except (TypeError, ValueError) as exc:
        return False, f"Invalid numeric field type: {exc}"

    if not (MIN_PLAUSIBLE_VOLTAGE_V <= v <= MAX_PLAUSIBLE_VOLTAGE_V):
        return False, f"Voltage {v}V out of plausible bounds [50, 300]"
    if not (0.0 <= i <= MAX_PLAUSIBLE_CURRENT_A):
        return False, f"Current {i}A out of plausible bounds [0, 50]"
    if p < 0.0:
        return False, f"Active power {p}W cannot be negative"
    if not (0.0 <= pf <= 1.0):
        return False, f"Power factor {pf} out of bounds [0.0, 1.0]"
    if not (MIN_PLAUSIBLE_FREQ_HZ <= f_val <= MAX_PLAUSIBLE_FREQ_HZ):
        return False, f"Frequency {f_val}Hz out of plausible bounds [40, 65]"
    if e_kwh < 0.0:
        return False, f"Energy {e_kwh}kWh cannot be negative"

    return True, None


def compute_powers(v: float, i: float, p: float) -> Tuple[float, float]:
    """Compute apparent power S (VA) and reactive power Q (VAr) in the backend.
    
    Per contract §2.3 and §5: The device publishes only measured fields;
    S and Q must be calculated by the backend/dashboard.
    """
    s = round(v * i, 2)
    diff = max(0.0, (s * s) - (p * p))
    q = round(math.sqrt(diff), 2)
    return s, q


def ingest_telemetry_packet(
    db: Session,
    device_id: str,
    ch: int,
    data: dict[str, Any],
    broadcast_fn: Optional[Callable[[str, dict[str, Any]], Any]] = None,
) -> Tuple[bool, Optional[Telemetry], Optional[str]]:
    """Validate, enrich, persist, and evaluate an incoming telemetry packet."""
    is_valid, reason = validate_telemetry_reading(data)
    if not is_valid:
        logger.warning("Quarantining invalid telemetry on %s CH %d: %s", device_id, ch, reason)
        return False, None, reason

    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device:
        return False, None, f"Device {device_id} not registered"

    if ch not in (1, 2):
        return False, None, f"Invalid channel number {ch}"

    ts_epoch = float(data["ts"])
    recorded_at = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

    # Compute derived powers
    v_val = float(data["v"])
    i_val = float(data["i"])
    p_val = float(data["p"])
    s_val, q_val = compute_powers(v_val, i_val, p_val)

    # Idempotency / duplicate protection
    existing = db.scalar(
        select(Telemetry).where(
            Telemetry.device_pk == device.id,
            Telemetry.ch == ch,
            Telemetry.ts == recorded_at,
        )
    )
    if existing:
        return True, existing, None

    v_dec = Decimal(str(round(v_val, 2)))
    i_dec = Decimal(str(round(i_val, 3)))
    p_dec = Decimal(str(round(p_val, 2)))
    pf_dec = Decimal(str(round(float(data["pf"]), 3)))
    f_dec = Decimal(str(round(float(data["f"]), 2)))
    e_dec = Decimal(str(round(float(data["e_kwh"]), 3)))

    state_str = normalize_channel_state(str(data.get("state", "OFF")))
    is_buffered = bool(data.get("buffered", False))

    telemetry = Telemetry(
        device_pk=device.id,
        ch=ch,
        ts=recorded_at,
        v=v_dec,
        i=i_dec,
        p=p_dec,
        pf=pf_dec,
        f=f_dec,
        e_kwh=e_dec,
        relay=bool(data["relay"]),
        state=state_str,
        buffered=is_buffered,
        clock_synced=bool(data.get("clock_synced", True)),
        boot_id=data.get("boot_id"),
        seq=data.get("seq"),
    )
    db.add(telemetry)

    # Update channel live tracking
    channel = db.scalar(
        select(Channel).where(
            Channel.device_pk == device.id,
            Channel.ch == ch,
        )
    )
    if channel:
        channel.last_telemetry_at = recorded_at
        channel.relay_commanded = telemetry.relay
        channel.state = state_str
        channel.updated_at = datetime.now(timezone.utc)

    # Update device online state
    now_utc = datetime.now(timezone.utc)
    device.online = True
    device.last_seen_at = now_utc

    db.commit()

    # Broadcast to live WebSocket clients
    if broadcast_fn:
        live_payload = {
            "type": "telemetry",
            "device_id": device_id,
            "ch": ch,
            "ts": ts_epoch,
            "v": v_val,
            "i": i_val,
            "p": p_val,
            "s": s_val,
            "q": q_val,
            "pf": float(data["pf"]),
            "f": float(data["f"]),
            "e_kwh": float(data["e_kwh"]),
            "relay": telemetry.relay,
            "state": state_str,
            "buffered": is_buffered,
        }
        try:
            broadcast_fn(device_id, live_payload)
        except Exception as exc:
            logger.debug("Broadcast error: %s", exc)

    # Workstream 5 Rule 3 & 4:
    # If buffered=true, skip live recognition and anomaly checks (it is past data)
    if not is_buffered:
        # Run anomaly check if a confirmed profile exists for this channel
        profile = db.scalar(
            select(LoadProfile).where(
                LoadProfile.owner_id == device.owner_id,
                LoadProfile.channel_last_seen == ch,
                LoadProfile.user_confirmed == True,  # noqa: E712
            )
        )
        if profile and profile.fingerprints:
            detector = AnomalyDetector(db)
            sample = ReadingSample(
                voltage_v=v_val,
                current_a=i_val,
                active_power_w=p_val,
                power_factor=float(data["pf"]),
                frequency_hz=float(data["f"]),
                timestamp_s=ts_epoch,
            )
            eval_res = detector.evaluate_sample(sample, profile.fingerprints[0])
            if eval_res.is_anomaly and not eval_res.is_transient_inrush:
                detector.record_anomaly_event(device.id, ch, eval_res)

    return True, telemetry, None


def ingest_event_packet(
    db: Session,
    device_id: str,
    data: dict[str, Any],
) -> Tuple[bool, Optional[Event], Optional[str]]:
    """Persist a device event from panel/{DEVICE_ID}/event."""
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device:
        return False, None, f"Device {device_id} not registered"

    event_id_str = data.get("event_id")
    if not event_id_str:
        return False, None, "Missing event_id"

    try:
        event_uuid = uuid.UUID(str(event_id_str))
    except ValueError:
        return False, None, "Invalid event_id UUID format"

    # De-duplicate per contract §7
    existing = db.scalar(select(Event).where(Event.id == event_uuid))
    if existing:
        return True, existing, None

    ts_epoch = float(data.get("ts", datetime.now(timezone.utc).timestamp()))
    event_ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

    ch_val = data.get("ch")
    ch_int = int(ch_val) if ch_val in (1, 2) else None

    severity = str(data.get("severity", "info")).lower()
    if severity not in ("info", "warning", "critical"):
        severity = "info"

    event = Event(
        id=event_uuid,
        device_pk=device.id,
        ch=ch_int,
        ts=event_ts,
        type=str(data.get("type", "UNKNOWN")),
        severity=severity,
        message=str(data.get("message", "Device event"))[:200],
        data=data.get("data"),
    )
    db.add(event)
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return True, event, None


def ingest_status_packet(db: Session, device_id: str, data: dict[str, Any]) -> None:
    """Handle status / LWT payload from panel/{DEVICE_ID}/status."""
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device:
        return

    is_online = bool(data.get("online", True))
    reason = str(data.get("reason", ""))

    now_utc = datetime.now(timezone.utc)
    if not is_online or reason == "lwt":
        device.online = False
        # Emit disconnect event
        event = Event(
            id=uuid.uuid4(),
            device_pk=device.id,
            ch=None,
            ts=now_utc,
            type="DEVICE_OFFLINE",
            severity="warning",
            message=f"Device {device_id} went offline (reason: {reason or 'disconnect'})",
            data=data,
        )
        db.add(event)
    else:
        device.online = True
        device.last_seen_at = now_utc
        if "fw" in data:
            device.fw_version = str(data["fw"])
        device.last_status = data

    db.commit()


def ingest_heartbeat_packet(db: Session, device_id: str, data: dict[str, Any]) -> None:
    """Update device health and last_seen from panel/{DEVICE_ID}/heartbeat."""
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device:
        return

    device.online = True
    device.last_seen_at = datetime.now(timezone.utc)
    device.last_status = data
    db.commit()


def check_offline_devices(db: Session, timeout_seconds: int = 15) -> list[Device]:
    """Find active devices that missed telemetry/heartbeats for >15s and mark them offline."""
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(seconds=timeout_seconds)

    stale_devices = list(
        db.scalars(
            select(Device).where(
                Device.online == True,  # noqa: E712
                Device.last_seen_at < cutoff,
            )
        ).all()
    )

    for dev in stale_devices:
        dev.online = False
        event = Event(
            id=uuid.uuid4(),
            device_pk=dev.id,
            ch=None,
            ts=now_utc,
            type="DEVICE_OFFLINE",
            severity="warning",
            message=f"Device {dev.device_id} timed out after {timeout_seconds}s without telemetry/heartbeat",
        )
        db.add(event)

    if stale_devices:
        db.commit()

    return stale_devices


class LiveMQTTSubscriber:
    """Background MQTT subscriber for live panel telemetry, events, acks, and status."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Optional[mqtt.Client] = None
        self._is_running = False

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        # rc can be an integer or ReasonCode object in v2
        rc_code = getattr(rc, "value", rc)
        if rc_code == 0:
            logger.info("LiveMQTTSubscriber connected to broker at %s:%d", self.settings.mqtt_host, self.settings.mqtt_port)
            client.subscribe("panel/+/telemetry/+", qos=1)
            client.subscribe("panel/+/event", qos=1)
            client.subscribe("panel/+/status", qos=1)
            client.subscribe("panel/+/heartbeat", qos=1)
            client.subscribe("panel/+/ack", qos=1)
        else:
            logger.warning("LiveMQTTSubscriber broker connection failed with code %s", rc)

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic_parts = msg.topic.split("/")
            # topic structure: panel/{device_id}/{type}[/{ch}]
            if len(topic_parts) < 3 or topic_parts[0] != "panel":
                return

            device_id = topic_parts[1]
            msg_type = topic_parts[2]

            with SessionLocal() as db:
                if msg_type == "telemetry" and len(topic_parts) >= 4:
                    ch = int(topic_parts[3])
                    ingest_telemetry_packet(db, device_id, ch, payload)
                elif msg_type == "event":
                    ingest_event_packet(db, device_id, payload)
                elif msg_type == "status":
                    ingest_status_packet(db, device_id, payload)
                elif msg_type == "heartbeat":
                    ingest_heartbeat_packet(db, device_id, payload)
                elif msg_type == "ack":
                    ack_in = CommandAckIn.model_validate(payload)
                    handle_command_ack(db, ack_in)

        except Exception as exc:
            logger.error("Error processing MQTT message on topic %s: %s", msg.topic, exc)

    def start(self) -> None:
        """Start non-blocking MQTT loop in background thread."""
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"{self.settings.mqtt_client_id}-live",
            )
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, 60)
            self.client.loop_start()
            self._is_running = True
            logger.info("LiveMQTTSubscriber started background loop")
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not start LiveMQTTSubscriber: %s", exc)

    def stop(self) -> None:
        """Gracefully disconnect and stop background loop."""
        if self.client and self._is_running:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self._is_running = False
            logger.info("LiveMQTTSubscriber stopped cleanly")


subscriber = LiveMQTTSubscriber()
