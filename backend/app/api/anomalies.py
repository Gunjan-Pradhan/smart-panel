"""REST API endpoints for Anomaly Detection Engine."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.models.event import Event
from app.models.load_profile import LoadProfile
from app.models.user import User
from app.schemas.anomaly import (
    AnomalyCheckRequest,
    AnomalyCheckResponse,
    AnomalyEventResponse,
    ZScoreMetrics,
)
from app.services.anomaly_detector import AnomalyDetector
from app.services.fingerprint import ReadingSample

router = APIRouter(tags=["anomaly-detection"])


@router.post(
    "/channels/{ch}/anomalies/check",
    response_model=AnomalyCheckResponse,
    status_code=status.HTTP_200_OK,
)
def check_anomaly(
    ch: Annotated[int, Path(ge=1, le=2)],
    payload: AnomalyCheckRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Evaluates telemetry sample against profile baseline and detects electrical anomalies."""
    # Find target profile
    profile: LoadProfile | None = None
    if payload.profile_id:
        profile = db.get(LoadProfile, payload.profile_id)
        if not profile or profile.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified profile not found",
            )
    else:
        # Get active profile on this channel for user
        stmt = (
            select(LoadProfile)
            .where(
                LoadProfile.owner_id == current_user.id,
                LoadProfile.channel_last_seen == ch,
            )
            .order_by(LoadProfile.created_at.desc())
        )
        profile = db.execute(stmt).scalars().first()

    if not profile or not profile.fingerprints:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No baseline load profile exists for Channel {ch}. Learn a profile first.",
        )

    fp = profile.fingerprints[-1]
    detector = AnomalyDetector(db)
    sample = ReadingSample(
        voltage_v=payload.sample.voltage_v,
        current_a=payload.sample.current_a,
        active_power_w=payload.sample.active_power_w,
        power_factor=payload.sample.power_factor,
        frequency_hz=payload.sample.frequency_hz,
        timestamp_s=payload.sample.timestamp_s,
    )

    evaluation = detector.evaluate_sample(
        sample=sample,
        fp=fp,
        is_startup_window=payload.is_startup_window,
    )

    # If critical or warning, attempt to find user's device and log event
    if evaluation.is_anomaly:
        device_stmt = select(Device).where(Device.owner_id == current_user.id).limit(1)
        device = db.execute(device_stmt).scalars().first()
        if device:
            detector.record_anomaly_event(
                device_pk=device.id,
                channel=ch,
                evaluation=evaluation,
            )

    return AnomalyCheckResponse(
        is_anomaly=evaluation.is_anomaly,
        severity=evaluation.severity,  # type: ignore
        flags=evaluation.flags,
        is_transient_inrush=evaluation.is_transient_inrush,
        z_scores=ZScoreMetrics(
            z_voltage=evaluation.z_scores.z_voltage,
            z_current=evaluation.z_scores.z_current,
            z_power=evaluation.z_scores.z_power,
            z_power_factor=evaluation.z_scores.z_power_factor,
            max_z=evaluation.z_scores.max_z,
        ),
        isolation_score=evaluation.isolation_score,
        message=evaluation.message,
        details=evaluation.details,
    )


@router.get(
    "/channels/{ch}/anomalies/events",
    response_model=list[AnomalyEventResponse],
)
def get_channel_anomaly_events(
    ch: Annotated[int, Path(ge=1, le=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Retrieves recent anomaly events logged for this channel."""
    device_stmt = select(Device).where(Device.owner_id == current_user.id).limit(1)
    device = db.execute(device_stmt).scalars().first()
    if not device:
        return []

    detector = AnomalyDetector(db)
    return detector.get_recent_anomaly_events(
        device_pk=device.id,
        channel=ch,
        limit=limit,
    )

