"""REST API endpoints for load profiles and learning sessions.

Protects all endpoints with JWT auth and enforces strict ownership.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.load_profile import LearningSession, LoadProfile
from app.models.user import User
from app.schemas.load_profile import (
    LearningSessionResponse,
    LoadProfileCreate,
    LoadProfileResponse,
    LoadProfileUpdate,
    StartLearningRequest,
)
from app.services.learning_manager import LearningSessionManager

router = APIRouter(tags=["learning-and-profiles"])


# --------------------------------------------------------------------------
# Learning Session Endpoints
# --------------------------------------------------------------------------


@router.post(
    "/channels/{ch}/learning/start",
    response_model=LearningSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_learning(
    ch: Annotated[int, Path(ge=1, le=2)],
    request: StartLearningRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Starts a learning session on channel 1 or 2."""
    manager = LearningSessionManager(db)
    session = manager.start_session(channel=ch, is_simulated=request.is_simulated)
    return session


@router.get(
    "/channels/{ch}/learning/status",
    response_model=LearningSessionResponse | None,
)
def get_learning_status(
    ch: Annotated[int, Path(ge=1, le=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Gets the active learning session on a channel."""
    manager = LearningSessionManager(db)
    session = manager.get_active_session(channel=ch)
    return session


@router.post(
    "/learning/{session_id}/cancel",
    response_model=LearningSessionResponse,
)
def cancel_learning(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Cancels an active learning session."""
    manager = LearningSessionManager(db)
    session = manager.cancel_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return session


# --------------------------------------------------------------------------
# Load Profile Management Endpoints
# --------------------------------------------------------------------------


@router.get("/profiles", response_model=list[LoadProfileResponse])
def list_profiles(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Lists all saved load profiles owned by the current user."""
    stmt = (
        select(LoadProfile)
        .where(LoadProfile.owner_id == current_user.id)
        .order_by(LoadProfile.created_at.desc())
    )
    return db.execute(stmt).scalars().all()


@router.post(
    "/profiles",
    response_model=LoadProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    payload: LoadProfileCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Manually creates a new load profile."""
    profile = LoadProfile(
        owner_id=current_user.id,
        display_name=payload.display_name,
        channel_last_seen=payload.channel_last_seen,
        nominal_power_w=payload.nominal_power_w,
        nominal_current_a=payload.nominal_current_a,
        notes=payload.notes,
        user_confirmed=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/profiles/{profile_id}", response_model=LoadProfileResponse)
def update_profile(
    profile_id: uuid.UUID,
    payload: LoadProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Updates display name or notes of an owned profile."""
    profile = db.get(LoadProfile, profile_id)
    if not profile or profile.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    if payload.display_name is not None:
        profile.display_name = payload.display_name
    if payload.notes is not None:
        profile.notes = payload.notes

    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profiles/{profile_id}/confirm", response_model=LoadProfileResponse)
def confirm_profile(
    profile_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Marks a load profile as explicitly user-confirmed."""
    profile = db.get(LoadProfile, profile_id)
    if not profile or profile.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    profile.user_confirmed = True
    db.commit()
    db.refresh(profile)
    return profile

