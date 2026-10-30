"""REST API endpoints for Load Recognition Engine."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.load_profile import RecognitionEvent
from app.models.user import User
from app.schemas.recognition import (
    RecognitionEventResponse,
    RecognitionFeedbackRequest,
    RecognizeWindowRequest,
)
from app.services.fingerprint import ReadingSample
from app.services.recognition import RecognitionEngine

router = APIRouter(tags=["recognition"])


@router.post(
    "/channels/{ch}/recognize",
    response_model=RecognitionEventResponse,
    status_code=status.HTTP_200_OK,
)
def recognize_window(
    ch: Annotated[int, Path(ge=1, le=2)],
    request: RecognizeWindowRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Evaluates telemetry in an observation window and classifies current load."""
    engine = RecognitionEngine(db)
    samples = [
        ReadingSample(
            voltage_v=s.voltage_v,
            current_a=s.current_a,
            active_power_w=s.active_power_w,
            power_factor=s.power_factor,
            frequency_hz=s.frequency_hz,
            timestamp_s=s.timestamp_s,
        )
        for s in request.samples
    ]
    event = engine.recognize_and_record(
        channel=ch,
        owner_id=current_user.id,
        samples=samples,
    )
    return event


@router.get(
    "/channels/{ch}/recognition/latest",
    response_model=RecognitionEventResponse | None,
)
def get_latest_recognition(
    ch: Annotated[int, Path(ge=1, le=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Retrieves the most recent recognition event on a channel."""
    stmt = (
        select(RecognitionEvent)
        .where(RecognitionEvent.channel == ch)
        .order_by(desc(RecognitionEvent.recognized_at))
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


@router.get(
    "/channels/{ch}/recognition/history",
    response_model=list[RecognitionEventResponse],
)
def get_recognition_history(
    ch: Annotated[int, Path(ge=1, le=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Retrieves recognition history on a channel."""
    stmt = (
        select(RecognitionEvent)
        .where(RecognitionEvent.channel == ch)
        .order_by(desc(RecognitionEvent.recognized_at))
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/recognition/{event_id}/feedback",
    response_model=RecognitionEventResponse,
)
def submit_recognition_feedback(
    event_id: uuid.UUID,
    payload: RecognitionFeedbackRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Allows an operator to confirm or correct AI recognition."""
    engine = RecognitionEngine(db)
    event = engine.submit_feedback(
        event_id=event_id,
        user_feedback=payload.user_feedback,
        corrected_profile_id=payload.corrected_profile_id,
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recognition event not found",
        )
    return event

