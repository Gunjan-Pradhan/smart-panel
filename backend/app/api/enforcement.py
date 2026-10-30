"""REST API endpoints for Runtime Mode Enforcement."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.models.user import User
from app.schemas.enforcement import (
    CommandValidationRequest,
    CommandValidationResponse,
    EnforcementEvaluationResponse,
    ModeEnforcementRequest,
    ModeStatusResponse,
)
from app.services.fingerprint import ReadingSample
from app.services.mode_enforcer import ModeEnforcer

router = APIRouter(tags=["mode-enforcement"])


@router.get(
    "/channels/{ch}/mode/status",
    response_model=ModeStatusResponse,
)
def get_channel_mode_status(
    ch: Annotated[int, Path(ge=1, le=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Retrieves current operating mode status and policy configuration for a channel."""
    enforcer = ModeEnforcer(db)
    profile, modes = enforcer.get_channel_modes(ch, current_user.id)
    mode_names = [m.mode_name for m in modes]

    return ModeStatusResponse(
        channel=ch,
        active_profile_id=profile.id if profile else None,
        active_profile_name=profile.display_name if profile else None,
        enabled_modes=mode_names,
        is_always_on="always_on" in mode_names,
        is_protection_active="protection" in mode_names,
        is_eco_active="eco" in mode_names,
        is_adaptive_filter_active="adaptive_filter" in mode_names,
        parameters={
            "nominal_power_w": float(profile.nominal_power_w) if profile and profile.nominal_power_w else None,
            "nominal_current_a": float(profile.nominal_current_a) if profile and profile.nominal_current_a else None,
        },
    )


@router.post(
    "/channels/{ch}/enforce",
    response_model=EnforcementEvaluationResponse,
    status_code=status.HTTP_200_OK,
)
def evaluate_mode_enforcement(
    ch: Annotated[int, Path(ge=1, le=2)],
    payload: ModeEnforcementRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Evaluates telemetry sample against active channel modes and generates advisories/alerts."""
    device_stmt = select(Device).where(Device.owner_id == current_user.id).limit(1)
    device = db.execute(device_stmt).scalars().first()

    enforcer = ModeEnforcer(db)
    sample = ReadingSample(
        voltage_v=payload.sample.voltage_v,
        current_a=payload.sample.current_a,
        active_power_w=payload.sample.active_power_w,
        power_factor=payload.sample.power_factor,
        frequency_hz=payload.sample.frequency_hz,
        timestamp_s=payload.sample.timestamp_s,
    )

    result = enforcer.evaluate_sample(
        channel=ch,
        owner_id=current_user.id,
        sample=sample,
        is_startup_window=payload.is_startup_window,
        current_hour=payload.current_hour,
        device_pk=device.id if device else None,
    )

    return EnforcementEvaluationResponse(
        channel=result.channel,
        active_modes=result.active_modes,
        status=result.status,  # type: ignore
        severity=result.severity,  # type: ignore
        advisories=result.advisories,
        event_logged=result.event_logged,
        details=result.details,
    )


@router.post(
    "/channels/{ch}/commands/validate",
    response_model=CommandValidationResponse,
    status_code=status.HTTP_200_OK,
)
def validate_channel_command(
    ch: Annotated[int, Path(ge=1, le=2)],
    payload: CommandValidationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Validates an outgoing relay command against active channel mode constraints."""
    enforcer = ModeEnforcer(db)
    allowed, reason, active_modes = enforcer.validate_command(
        channel=ch,
        owner_id=current_user.id,
        action=payload.action,
        force=payload.force,
    )

    return CommandValidationResponse(
        allowed=allowed,
        reason=reason,
        channel=ch,
        action=payload.action,
        active_modes=active_modes,
    )

