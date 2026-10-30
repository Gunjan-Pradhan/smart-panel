"""Pydantic schemas for Load Recognition Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.load_profile import LoadProfileResponse


class ReadingSampleSchema(BaseModel):
    voltage_v: float = Field(..., ge=0.0, le=500.0)
    current_a: float = Field(..., ge=0.0, le=100.0)
    active_power_w: float = Field(..., ge=0.0, le=50000.0)
    power_factor: float = Field(..., ge=-1.0, le=1.0)
    frequency_hz: float = Field(..., ge=40.0, le=70.0)
    timestamp_s: float | None = None


class RecognizeWindowRequest(BaseModel):
    samples: list[ReadingSampleSchema] = Field(
        ...,
        min_length=1,
        description="Telemetry samples in the observation window.",
    )


class RecognitionCandidateInfo(BaseModel):
    profile_id: uuid.UUID
    display_name: str
    similarity_score: float = Field(..., ge=0.0, le=100.0)


class RecognitionEventResponse(BaseModel):
    id: uuid.UUID
    channel: int
    recognized_at: datetime
    similarity_score: float
    state: Literal["recognized", "ambiguous", "unknown", "insufficient_data"]
    user_feedback: Literal["pending", "confirmed", "corrected"]
    best_candidate_id: uuid.UUID | None = None
    runner_up_id: uuid.UUID | None = None
    corrected_profile_id: uuid.UUID | None = None
    best_candidate: LoadProfileResponse | None = None
    runner_up: LoadProfileResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class RecognitionFeedbackRequest(BaseModel):
    user_feedback: Literal["confirmed", "corrected"]
    corrected_profile_id: uuid.UUID | None = None
