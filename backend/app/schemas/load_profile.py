"""Pydantic schemas for load profiles, learning sessions, and fingerprints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StartLearningRequest(BaseModel):
    duration_seconds: int = Field(default=300, ge=10, le=1800)
    is_simulated: bool = False


class LearningSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: int
    status: str
    valid_count: int
    excluded_count: int
    sampling_interval_s: float | None = None
    feature_set_version: str
    is_simulated: bool
    start_time: datetime
    end_time: datetime | None = None


class LoadProfileCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    channel_last_seen: int | None = Field(default=None, ge=1, le=2)
    nominal_power_w: Decimal | None = None
    nominal_current_a: Decimal | None = None
    notes: str | None = None


class LoadProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = None


class ConfirmLimitsRequest(BaseModel):
    current_limit_a: Decimal | None = Field(default=None, ge=Decimal("0.1"), le=Decimal("50.0"))
    power_limit_w: Decimal | None = Field(default=None, ge=Decimal("1.0"), le=Decimal("10000.0"))
    voltage_min_v: Decimal | None = Field(default=None, ge=Decimal("100.0"), le=Decimal("250.0"))
    voltage_max_v: Decimal | None = Field(default=None, ge=Decimal("200.0"), le=Decimal("300.0"))
    inrush_blanking_ms: int | None = Field(default=None, ge=0, le=10000)


class LoadProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    user_confirmed: bool
    channel_last_seen: int | None
    nominal_power_w: Decimal | None
    nominal_current_a: Decimal | None
    notes: str | None
    proposed_current_limit_a: Decimal | None = None
    proposed_power_limit_w: Decimal | None = None
    proposed_voltage_min_v: Decimal | None = None
    proposed_voltage_max_v: Decimal | None = None
    proposed_inrush_blanking_ms: int | None = None
    limits_status: str = "NONE"
    confirmed_current_limit_a: Decimal | None = None
    confirmed_power_limit_w: Decimal | None = None
    confirmed_voltage_min_v: Decimal | None = None
    confirmed_voltage_max_v: Decimal | None = None
    confirmed_inrush_blanking_ms: int | None = None
    limits_confirmed_by: uuid.UUID | None = None
    limits_confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

