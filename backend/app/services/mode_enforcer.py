"""Runtime Mode Enforcement Service.

Enforces operator-accepted operating modes (protection, always_on, eco, adaptive_filter):
- Evaluates live telemetry against mode constraints
- Recommends alerts on motor stall / overcurrent in Protection Mode
- Guards against accidental relay cutoff on Always-On baselines
- Emits energy curfew advisories in Eco Mode
- Non-negotiable boundary: AI NEVER switches a relay directly; all actions are advisory.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.load_profile import LoadModeSelection, LoadProfile
from app.services.fingerprint import ReadingSample


@dataclass(frozen=True)
class EnforcementResult:
    channel: int
    active_modes: list[str]
    status: str  # "normal", "alert", "advisory", "inrush_transient"
    severity: str  # "info", "warning", "critical"
    advisories: list[str]
    event_logged: bool
    details: dict[str, Any]


class ModeEnforcer:
    """Enforces mode policies and validates commands against mode rules."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_channel_modes(
        self,
        channel: int,
        owner_id: uuid.UUID,
    ) -> tuple[LoadProfile | None, list[LoadModeSelection]]:
        """Retrieves active profile and enabled modes for a channel."""
        stmt = (
            select(LoadProfile)
            .where(
                LoadProfile.owner_id == owner_id,
                LoadProfile.channel_last_seen == channel,
            )
            .order_by(desc(LoadProfile.created_at))
        )
        profile = self.db.execute(stmt).scalars().first()
        if not profile:
            return None, []

        stmt_modes = select(LoadModeSelection).where(
            LoadModeSelection.profile_id == profile.id,
            LoadModeSelection.enabled == True,  # noqa: E712
        )
        modes = list(self.db.execute(stmt_modes).scalars().all())
        return profile, modes

    def validate_command(
        self,
        channel: int,
        owner_id: uuid.UUID,
        action: str,
        force: bool = False,
    ) -> tuple[bool, str, list[str]]:
        """Validates an outgoing relay command against active channel mode constraints."""
        _, modes = self.get_channel_modes(channel, owner_id)
        mode_names = [m.mode_name for m in modes]

        if "always_on" in mode_names and action.upper() == "OFF":
            if not force:
                return (
                    False,
                    "Channel is configured in Always-On baseline mode. Accidental power cutoff is prevented unless force=true.",
                    mode_names,
                )
            return (
                True,
                "Command allowed via explicit operator force override.",
                mode_names,
            )

        return (
            True,
            "Command allowed under active mode constraints.",
            mode_names,
        )

    def evaluate_sample(
        self,
        channel: int,
        owner_id: uuid.UUID,
        sample: ReadingSample,
        is_startup_window: bool = False,
        current_hour: int | None = None,
        device_pk: uuid.UUID | None = None,
    ) -> EnforcementResult:
        """Evaluates a live telemetry sample under active mode rules."""
        profile, modes = self.get_channel_modes(channel, owner_id)
        mode_names = [m.mode_name for m in modes]

        advisories: list[str] = []
        status = "normal"
        severity = "info"
        event_logged = False
        details: dict[str, Any] = {
            "channel": channel,
            "profile_name": profile.display_name if profile else None,
            "sample": {
                "voltage": sample.voltage_v,
                "current": sample.current_a,
                "power": sample.active_power_w,
                "pf": sample.power_factor,
            },
        }

        # 1. Protection Mode (Motor stall and inrush evaluation)
        if "protection" in mode_names:
            nominal_current = float(profile.nominal_current_a or 0.82) if profile else 0.82
            stall_threshold = round(1.5 * nominal_current, 3)
            details["protection"] = {
                "nominal_current": nominal_current,
                "stall_threshold": stall_threshold,
            }

            if sample.current_a >= stall_threshold:
                if is_startup_window:
                    status = "inrush_transient"
                    severity = "info"
                    advisories.append(
                        f"Protection Mode: High current ({sample.current_a:.2f}A) detected during startup window. "
                        f"Direct-on-line inrush surge recognized; alert suppressed."
                    )
                else:
                    status = "alert"
                    severity = "critical"
                    msg = (
                        f"Protection Mode Alert: Sustained current {sample.current_a:.2f}A exceeds "
                        f"stall threshold {stall_threshold:.2f}A. High probability of rotor stall or mechanical jam."
                    )
                    advisories.append(msg)
                    if device_pk:
                        self._log_event(
                            device_pk=device_pk,
                            channel=channel,
                            event_type="mode_alert_stall",
                            severity="critical",
                            message=msg,
                            data=details,
                        )
                        event_logged = True

        # 2. Eco Mode (Curfew and energy waste tracking)
        if "eco" in mode_names:
            hr = current_hour if current_hour is not None else datetime.now(timezone.utc).hour
            is_curfew = hr >= 23 or hr < 6
            details["eco"] = {"hour": hr, "is_curfew": is_curfew}

            if is_curfew and sample.active_power_w > 15.0:
                if status != "alert":
                    status = "advisory"
                    severity = "info"
                msg = (
                    f"Eco Mode Advisory: Load active ({sample.active_power_w:.1f}W) during scheduled "
                    f"curfew hours (23:00-06:00). Consider powering down to save energy."
                )
                advisories.append(msg)
                if device_pk and not event_logged:
                    self._log_event(
                        device_pk=device_pk,
                        channel=channel,
                        event_type="mode_advisory_curfew",
                        severity="info",
                        message=msg,
                        data=details,
                    )
                    event_logged = True

        # 3. Always-On Mode
        if "always_on" in mode_names:
            advisories.append("Always-On Mode active: Relay is guarded against unintentional disconnect.")

        # 4. Adaptive Filter Mode
        if "adaptive_filter" in mode_names:
            advisories.append("Adaptive Trip Smoothing active: Filtering transient power variations.")

        if not advisories:
            advisories.append("Nominal operation under active mode policies.")

        return EnforcementResult(
            channel=channel,
            active_modes=mode_names,
            status=status,
            severity=severity,
            advisories=advisories,
            event_logged=event_logged,
            details=details,
        )

    def _log_event(
        self,
        device_pk: uuid.UUID,
        channel: int,
        event_type: str,
        severity: str,
        message: str,
        data: dict[str, Any],
    ) -> Event:
        event = Event(
            id=uuid.uuid4(),
            device_pk=device_pk,
            ch=channel,
            ts=datetime.now(timezone.utc),
            type=event_type,
            severity=severity,
            message=message,
            data=data,
            received_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.commit()
        return event

