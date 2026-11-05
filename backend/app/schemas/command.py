"""Pydantic schemas for device commands and acknowledgements."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommandCreate(BaseModel):
    """Payload to issue a command to a device channel."""

    ch: int = Field(..., description="Channel number (1 or 2)")
    action: Literal["ON", "OFF"] = Field(..., description="Relay action ('ON' or 'OFF')")
    duration_seconds: int | None = Field(
        default=None,
        description="Optional duration in seconds for timed operation (must be > 0)",
        gt=0,
    )
    priority: Literal["safety", "schedule", "user", "optimization", "advisory"] = Field(
        default="user",
        description="Command priority level",
    )
    source: Literal["user", "schedule", "system", "optimization"] = Field(
        default="user",
        description="Origin of the command",
    )

    @field_validator("ch")
    @classmethod
    def validate_channel(cls, v: int) -> int:
        if v not in (1, 2):
            raise ValueError("Channel must be 1 or 2")
        return v


class CommandAckIn(BaseModel):
    """Payload received from device on panel/{DEVICE_ID}/ack."""

    schema_version: int = Field(default=1, alias="schema")
    cmd_id: uuid.UUID = Field(..., description="Command UUID echo")
    ch: int = Field(..., description="Channel number echo")
    result: Literal["DONE", "REJECTED", "REFUSED", "FAILED"] = Field(
        ..., description="Execution outcome"
    )
    reason: str = Field(default="OK", description="Outcome reason code")
    relay: bool = Field(..., description="Current relay state after command")
    state: str | None = Field(default=None, description="Current channel state name")
    ts: float | None = Field(default=None, description="Device timestamp epoch seconds")

    model_config = ConfigDict(populate_by_name=True)


class CommandOut(BaseModel):
    """Public representation of a command record."""

    cmd_id: uuid.UUID
    device_id: str
    ch: int
    action: str
    source: str
    priority: str | None = None
    duration_seconds: int | None = None
    status: str
    reason: str | None = None
    issued_at: datetime
    expires_at: datetime
    acked_at: datetime | None = None
    executed_at: datetime | None = None
    relay_after: bool | None = None
    state_after: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

