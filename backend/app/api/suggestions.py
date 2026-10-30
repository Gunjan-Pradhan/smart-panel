"""REST API endpoints for Optimization Mode Suggestions and Mode Selections."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.load_profile import (
    LearningSession,
    LoadModeSelection,
    LoadProfile,
    ModeSuggestion,
)
from app.models.user import User
from app.schemas.suggestions import (
    LoadModeSelectionResponse,
    ModeSuggestionResponse,
)
from app.services.mode_suggester import ModeSuggester

router = APIRouter(tags=["mode-suggestions"])


@router.get(
    "/channels/{ch}/suggestions",
    response_model=list[ModeSuggestionResponse],
)
def get_channel_suggestions(
    ch: Annotated[int, Path(ge=1, le=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Retrieves AI mode suggestions for the latest learning session on a channel."""
    # Find latest ready learning session on this channel
    stmt = (
        select(LearningSession)
        .where(
            LearningSession.channel == ch,
            LearningSession.status == "ready",
        )
        .order_by(desc(LearningSession.start_time))
        .limit(1)
    )
    session = db.execute(stmt).scalars().first()
    if not session:
        return []

    suggester = ModeSuggester(db)
    return suggester.get_suggestions_by_session(session.id)


@router.get(
    "/profiles/{profile_id}/suggestions",
    response_model=list[ModeSuggestionResponse],
)
def get_profile_suggestions(
    profile_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Retrieves mode suggestions generated for a user-owned profile."""
    profile = db.get(LoadProfile, profile_id)
    if not profile or profile.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    suggester = ModeSuggester(db)
    return suggester.get_suggestions_for_profile(profile_id)


@router.post(
    "/suggestions/{suggestion_id}/accept",
    response_model=LoadModeSelectionResponse,
    status_code=status.HTTP_200_OK,
)
def accept_suggestion(
    suggestion_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Operator accepts an AI optimization suggestion, enabling that mode for the profile."""
    suggestion = db.get(ModeSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suggestion not found",
        )

    suggester = ModeSuggester(db)
    try:
        selection = suggester.accept_suggestion(suggestion_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return selection


@router.get(
    "/profiles/{profile_id}/modes",
    response_model=list[LoadModeSelectionResponse],
)
def get_profile_active_modes(
    profile_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Retrieves user-confirmed operating modes enabled for a profile."""
    profile = db.get(LoadProfile, profile_id)
    if not profile or profile.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    stmt = select(LoadModeSelection).where(
        LoadModeSelection.profile_id == profile_id
    )
    return list(db.execute(stmt).scalars().all())

