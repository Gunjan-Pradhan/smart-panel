"""Pydantic schemas for Mode Suggestions and Selections."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ModeSuggestionResponse(BaseModel):
    id: uuid.UUID
    learning_session_id: uuid.UUID
    mode_name: str
    rule_id: str
    reason_text: str
    triggering_values: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoadModeSelectionResponse(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    mode_name: str
    enabled: bool
    source: str
    selected_by: uuid.UUID | None = None
    selected_at: datetime

    model_config = ConfigDict(from_attributes=True)

