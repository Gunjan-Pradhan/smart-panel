"""MQTT adapter for translating ESP32 PZEM telemetry into validated database records.

Encapsulates all topic and field knowledge in one place.
Adheres to Section 3.2 and Section 5 of the build specification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

# Plausible electrical ranges for 230V single-phase AC
MIN_PLAUSIBLE_VOLTAGE_V = 50.0   # Below 50V is treated as no supply / dead line
MAX_PLAUSIBLE_VOLTAGE_V = 300.0  # Above 300V is an extreme surge / framing error
MAX_PLAUSIBLE_CURRENT_A = 50.0   # Current > 50A is physical overload or UART noise
MIN_PLAUSIBLE_FREQ_HZ = 40.0
MAX_PLAUSIBLE_FREQ_HZ = 65.0


@dataclass
class ParsedReading:
    """A single metric parsed from an MQTT topic."""

    channel: int
    metric_name: str
    value: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ChannelTelemetryRecord:
    """A full assembled electrical reading ready for database insertion."""

    channel: int
    recorded_at: datetime
    voltage_v: float
    current_a: float
    active_power_w: float
    apparent_power_va: float
    reactive_power_var: float
    power_factor: float
    frequency_hz: float
    energy_kwh: float
    relay_state: bool
    state: str
    validity: str  # 'valid', 'invalid', 'stale', 'simulated'
    is_simulated: bool = False
    validation_error: str | None = None


class MQTTTelemetryAdapter:
    """Parses individual firmware MQTT topics into structured channel records."""

    TOPIC_PREFIX = "energy/dual_pzem/"

    def __init__(self) -> None:
        # Buffer latest metrics per circuit until a full snapshot is assembled
        self._buffers: dict[int, dict[str, Any]] = {1: {}, 2: {}}

    def parse_topic(self, topic: str, payload_str: str) -> ParsedReading | None:
        """Parses an MQTT topic and string payload into a ParsedReading."""
        if not topic.startswith(self.TOPIC_PREFIX):
            return None

        subpath = topic[len(self.TOPIC_PREFIX):]  # e.g. "circuit1/voltage_V"
        parts = subpath.split("/")

        if len(parts) < 2:
            return None

        circuit_str = parts[0]
        if circuit_str == "circuit1":
            channel = 1
        elif circuit_str == "circuit2":
            channel = 2
        else:
            return None

        field_name = "/".join(parts[1:])
        payload_trimmed = payload_str.strip()

        # Parse type
        val: Any
        if payload_trimmed.upper() == "TRUE" or payload_trimmed.upper() == "ON":
            val = True
        elif payload_trimmed.upper() == "FALSE" or payload_trimmed.upper() == "OFF":
            val = False
        else:
            try:
                val = float(payload_trimmed)
            except ValueError:
                val = payload_trimmed

        return ParsedReading(channel=channel, metric_name=field_name, value=val)

    @staticmethod
    def validate_metrics(
        v: float,
        i: float,
        p: float,
        pf: float,
        f: float,
    ) -> tuple[bool, str | None]:
        """Validates electrical measurements against physical laws and plausible bounds."""
        for val, name in [(v, "voltage"), (i, "current"), (p, "power"), (pf, "pf"), (f, "frequency")]:
            if not math.isfinite(val):
                return False, f"Non-finite value for {name}: {val}"

        if v < 0 or i < 0 or p < 0:
            return False, f"Negative measurement not allowed: V={v}, I={i}, P={p}"

        if v > 0 and (v < MIN_PLAUSIBLE_VOLTAGE_V or v > MAX_PLAUSIBLE_VOLTAGE_V):
            return False, f"Voltage out of plausible bounds (50-300V): {v}V"

        if i > MAX_PLAUSIBLE_CURRENT_A:
            return False, f"Current exceeds plausible maximum (50A): {i}A"

        if pf < 0.0 or pf > 1.0:
            return False, f"Power factor outside [0.0, 1.0]: {pf}"

        if f > 0 and (f < MIN_PLAUSIBLE_FREQ_HZ or f > MAX_PLAUSIBLE_FREQ_HZ):
            return False, f"Grid frequency out of plausible bounds (40-65Hz): {f}Hz"

        return True, None

    def build_record(
        self,
        channel: int,
        v: float,
        i: float,
        p: float,
        pf: float,
        f: float,
        energy_kwh: float = 0.0,
        relay_state: bool = False,
        state: str = "RUNNING",
        is_simulated: bool = False,
        timestamp: datetime | None = None,
    ) -> ChannelTelemetryRecord:
        """Constructs a validated telemetry record, determining its validity status."""
        ts = timestamp or datetime.now(timezone.utc)
        is_valid, err_msg = self.validate_metrics(v, i, p, pf, f)

        if not is_valid:
            validity = "invalid"
        elif is_simulated:
            validity = "simulated"
        else:
            validity = "valid"

        # Derived calculations: S = V * I, Q = sqrt(S^2 - P^2)
        s = v * i
        # Clamp power to not exceed apparent power due to minor sensor rounding
        p_clamped = min(p, s)
        q = math.sqrt(max(0.0, s * s - p_clamped * p_clamped))

        return ChannelTelemetryRecord(
            channel=channel,
            recorded_at=ts,
            voltage_v=round(v, 2),
            current_a=round(i, 4),
            active_power_w=round(p, 2),
            apparent_power_va=round(s, 2),
            reactive_power_var=round(q, 2),
            power_factor=round(pf, 3),
            frequency_hz=round(f, 2),
            energy_kwh=round(energy_kwh, 4),
            relay_state=relay_state,
            state=state,
            validity=validity,
            is_simulated=is_simulated,
            validation_error=err_msg,
        )

