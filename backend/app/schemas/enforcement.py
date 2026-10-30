"""Pydantic schemas for Runtime Mode Enforcement."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LiveTelemetrySampleSchema(BaseModel):
    voltage_v: float = Field(..., ge=0.0, le=500.0)
    current_a: float = Field(..., ge=0.0, le=100.0)
    active_power_w: float = Field(..., ge=0.0, le=50000.0)
    power_factor: float = Field(..., ge=-1.0, le=1.0)
    frequency_hz: float = Field(default=50.0, ge=40.0, le=70.0)
    timestamp_s: float | None = None


class ModeEnforcementRequest(BaseModel):
    sample: LiveTelemetrySampleSchema
    is_startup_window: bool = False
    current_hour: int | None = Field(default=None, ge=0, le=23)


class ModeStatusResponse(BaseModel):
    channel: int
    active_profile_id: uuid.UUID | None = None
    active_profile_name: str | None = None
    enabled_modes: list[str]
    is_always_on: bool
    is_protection_active: bool
    is_eco_active: bool
    is_adaptive_filter_active: bool
    parameters: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class EnforcementEvaluationResponse(BaseModel):
    channel: int
    active_modes: list[str]
    status: Literal["normal", "alert", "advisory", "inrush_transient"]
    severity: Literal["info", "warning", "critical"]
    advisories: list[str]
    event_logged: bool
    details: dict[str, Any]


class CommandValidationRequest(BaseModel):
    action: Literal["ON", "OFF"]
    force: bool = False


class CommandValidationResponse(BaseModel):
    allowed: bool
    reason: str
    channel: int
    action: str
    active_modes: list[str]

