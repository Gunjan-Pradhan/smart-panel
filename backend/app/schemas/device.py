"""Pydantic response models for devices and channels."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ch: int
    name: str
    state: str
    relay_commanded: bool
    last_telemetry_at: datetime | None
    load_pk: uuid.UUID | None
    rated_voltage_v: float | None
    rated_current_a: float | None
    rated_power_w: float | None
    limit_voltage_min_v: float | None
    limit_voltage_max_v: float | None
    limit_current_a: float | None
    limit_power_w: float | None
    limit_freq_min_hz: float | None
    limit_freq_max_hz: float | None
    limit_pf_min: float | None
    limits_confirmed_at: datetime | None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: str
    name: str
    fw_version: str | None
    is_active: bool
    online: bool
    last_seen_at: datetime | None
    created_at: datetime
    channels: list[ChannelOut] = []
