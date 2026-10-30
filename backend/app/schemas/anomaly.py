"""Pydantic schemas for Anomaly Detection Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnomalyCheckSample(BaseModel):
    voltage_v: float = Field(..., ge=0.0, le=500.0)
    current_a: float = Field(..., ge=0.0, le=100.0)
    active_power_w: float = Field(..., ge=0.0, le=50000.0)
    power_factor: float = Field(..., ge=-1.0, le=1.0)
    frequency_hz: float = Field(default=50.0, ge=40.0, le=70.0)
    timestamp_s: float | None = None


class AnomalyCheckRequest(BaseModel):
    sample: AnomalyCheckSample
    profile_id: uuid.UUID | None = None
    is_startup_window: bool = False


class ZScoreMetrics(BaseModel):
    z_voltage: float
    z_current: float
    z_power: float
    z_power_factor: float
    max_z: float


class AnomalyCheckResponse(BaseModel):
    is_anomaly: bool
    severity: Literal["info", "warning", "critical"]
    flags: list[str]
    is_transient_inrush: bool
    z_scores: ZScoreMetrics
    isolation_score: float | None = None
    message: str
    details: dict[str, Any]


class AnomalyEventResponse(BaseModel):
    id: uuid.UUID
    device_pk: uuid.UUID
    ch: int | None
    ts: datetime
    type: str
    severity: str
    message: str
    data: dict[str, Any] | None = None
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)

