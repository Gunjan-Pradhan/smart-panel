"""Pydantic schemas for Schedule CRUD.

Schema reference: docs/database_schema.md §4.10 / Workstream 7.
"""

from __future__ import annotations

import uuid
from datetime import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ScheduleCreate(BaseModel):
    """Fields required to create a new schedule."""

    device_id: str = Field(..., description="Human-readable device ID, e.g. 'PANEL-0001'")
    ch: int = Field(..., ge=1, le=2, description="Channel number: 1 (Motor) or 2 (Sensitive)")
    name: str = Field(..., min_length=1, max_length=120)
    days_of_week: int = Field(
        ...,
        ge=1,
        le=127,
        description=(
            "Bitmask of days: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64. "
            "Combine with bitwise OR, e.g. Mon+Fri = 17."
        ),
    )
    on_time: time = Field(..., description="Time to turn ON the channel (local time, HH:MM:SS)")
    off_time: time = Field(..., description="Time to turn OFF the channel (local time, HH:MM:SS)")
    timezone: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="IANA timezone string, e.g. 'Asia/Kolkata'",
    )
    enabled: bool = Field(True, description="Whether this schedule is active")


class ScheduleUpdate(BaseModel):
    """All fields are optional — only provided fields are updated (PATCH semantics)."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    days_of_week: Optional[int] = Field(None, ge=1, le=127)
    on_time: Optional[time] = None
    off_time: Optional[time] = None
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)
    enabled: Optional[bool] = None


class ScheduleOut(BaseModel):
    """Full schedule representation returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: str = Field(..., description="Human-readable device ID")
    ch: int
    name: str
    days_of_week: int
    on_time: time
    off_time: time
    timezone: str
    enabled: bool

