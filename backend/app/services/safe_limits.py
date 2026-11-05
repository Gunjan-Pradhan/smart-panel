"""Safe limits policy, hard-cap boundaries, and operator confirmation logic.

Implements Workstream 3 of the capstone project specification:
- AI proposes safe operational limits upon fingerprinting.
- Confirmed limits are clamped against hardware hard-caps:
    Channel 1 (Induction Motor / Mechanical Relay):
        - Max Current: 16.0 A
        - Max Power: 3680.0 W
        - Voltage Range: 180.0 V - 265.0 V
        - Max Inrush Blanking: 3000 ms
    Channel 2 (Household / SSR-40DA):
        - Max Current: 10.0 A
        - Max Power: 2300.0 W
        - Voltage Range: 180.0 V - 265.0 V
        - Max Inrush Blanking: 3000 ms
- Hardware protection engine always enforces: min(confirmed, hard_cap).
- Audit trail written to audit_log table.
- Strict tenant isolation: foreign-owned profiles return 404.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.load_profile import LoadProfile
from app.models.user import User


@dataclass(frozen=True)
class ChannelHardCaps:
    channel: int
    max_current_a: Decimal
    max_power_w: Decimal
    min_voltage_v: Decimal
    max_voltage_v: Decimal
    max_inrush_blanking_ms: int


HARD_CAPS_CH1 = ChannelHardCaps(
    channel=1,
    max_current_a=Decimal("16.000"),
    max_power_w=Decimal("3680.00"),
    min_voltage_v=Decimal("180.00"),
    max_voltage_v=Decimal("265.00"),
    max_inrush_blanking_ms=3000,
)

HARD_CAPS_CH2 = ChannelHardCaps(
    channel=2,
    max_current_a=Decimal("10.000"),
    max_power_w=Decimal("2300.00"),
    min_voltage_v=Decimal("180.00"),
    max_voltage_v=Decimal("265.00"),
    max_inrush_blanking_ms=3000,
)


def get_channel_hard_caps(channel: int | None) -> ChannelHardCaps:
    """Returns the hard-cap safety envelope for the specified channel."""
    if channel == 1:
        return HARD_CAPS_CH1
    # Channel 2 or unassigned defaults to the more conservative CH2 caps
    return HARD_CAPS_CH2


def confirm_profile_limits(
    db: Session,
    profile: LoadProfile,
    user: User,
    requested_current: Decimal | None = None,
    requested_power: Decimal | None = None,
    requested_vmin: Decimal | None = None,
    requested_vmax: Decimal | None = None,
    requested_inrush: int | None = None,
    reason: str = "Operator confirmed limits",
) -> tuple[LoadProfile, bool]:
    """Confirms proposed limits or custom limits, clamping to hardware hard caps and logging an audit event."""
    caps = get_channel_hard_caps(profile.channel_last_seen)

    # 1. Fallback to proposed limits if requested is None
    target_current = requested_current if requested_current is not None else profile.proposed_current_limit_a
    target_power = requested_power if requested_power is not None else profile.proposed_power_limit_w
    target_vmin = requested_vmin if requested_vmin is not None else profile.proposed_voltage_min_v
    target_vmax = requested_vmax if requested_vmax is not None else profile.proposed_voltage_max_v
    target_inrush = requested_inrush if requested_inrush is not None else profile.proposed_inrush_blanking_ms

    if target_current is None or target_power is None or target_vmin is None or target_vmax is None:
        raise ValueError("Cannot confirm limits without proposed or requested limits")

    # 2. Hardware clamping to hard caps
    clamped_current = min(target_current, caps.max_current_a)
    clamped_power = min(target_power, caps.max_power_w)
    clamped_vmin = max(target_vmin, caps.min_voltage_v)
    clamped_vmax = min(target_vmax, caps.max_voltage_v)
    target_inrush_val = target_inrush if target_inrush is not None else 50
    clamped_inrush = min(target_inrush_val, caps.max_inrush_blanking_ms)

    was_clamped = (
        clamped_current != target_current
        or clamped_power != target_power
        or clamped_vmin != target_vmin
        or clamped_vmax != target_vmax
        or clamped_inrush != target_inrush_val
    )

    # 3. Create AuditLog entry
    audit_entry = AuditLog(
        action="CONFIRM_LIMITS",
        entity_type="load_profile",
        entity_id=str(profile.id),
        user_id=user.id,
        detail={
            "channel": profile.channel_last_seen,
            "old_status": profile.limits_status,
            "requested": {
                "current_limit_a": float(target_current),
                "power_limit_w": float(target_power),
                "voltage_min_v": float(target_vmin),
                "voltage_max_v": float(target_vmax),
                "inrush_blanking_ms": target_inrush_val,
            },
            "confirmed": {
                "current_limit_a": float(clamped_current),
                "power_limit_w": float(clamped_power),
                "voltage_min_v": float(clamped_vmin),
                "voltage_max_v": float(clamped_vmax),
                "inrush_blanking_ms": clamped_inrush,
            },
            "hard_caps": {
                "max_current_a": float(caps.max_current_a),
                "max_power_w": float(caps.max_power_w),
                "min_voltage_v": float(caps.min_voltage_v),
                "max_voltage_v": float(caps.max_voltage_v),
                "max_inrush_blanking_ms": caps.max_inrush_blanking_ms,
            },
            "clamped": was_clamped,
            "reason": reason,
        },
    )
    db.add(audit_entry)

    # 4. Update profile record
    profile.limits_status = "CONFIRMED"
    profile.confirmed_current_limit_a = clamped_current
    profile.confirmed_power_limit_w = clamped_power
    profile.confirmed_voltage_min_v = clamped_vmin
    profile.confirmed_voltage_max_v = clamped_vmax
    profile.confirmed_inrush_blanking_ms = clamped_inrush
    profile.limits_confirmed_by = user.id
    profile.limits_confirmed_at = datetime.now(timezone.utc)
    profile.user_confirmed = True

    db.commit()
    db.refresh(profile)
    return profile, was_clamped


def reject_profile_limits(
    db: Session,
    profile: LoadProfile,
    user: User,
    reason: str = "Operator rejected proposed limits",
) -> LoadProfile:
    """Rejects proposed limits, keeping previous limits or inactive state."""
    audit_entry = AuditLog(
        action="REJECT_LIMITS",
        entity_type="load_profile",
        entity_id=str(profile.id),
        user_id=user.id,
        detail={
            "old_status": profile.limits_status,
            "reason": reason,
        },
    )
    db.add(audit_entry)
    profile.limits_status = "REJECTED"
    db.commit()
    db.refresh(profile)
    return profile

