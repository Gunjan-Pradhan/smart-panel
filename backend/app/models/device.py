"""Devices (one ESP32 panel each).

Schema reference: docs/database_schema.md §4.3.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.channel import Channel
    from app.models.command import Command
    from app.models.event import Event
    from app.models.schedule import Schedule
    from app.models.telemetry import Telemetry
    from app.models.user import User

DEVICE_ID_PATTERN = r"^[A-Z0-9]{2,16}-[0-9]{4}$"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    device_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mqtt_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    fw_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_status: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    owner: Mapped["User"] = relationship(back_populates="devices")
    channels: Mapped[list["Channel"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    telemetry: Mapped[list["Telemetry"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    commands: Mapped[list["Command"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("device_id", name="uq_devices_device_id"),
        UniqueConstraint("mqtt_username", name="uq_devices_mqtt_username"),
        CheckConstraint(
            f"device_id ~ '{DEVICE_ID_PATTERN}'",
            name="device_id_format",
        ),
        Index("ix_devices_owner_id", "owner_id"),
        Index("ix_devices_last_seen_at", "last_seen_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Device(device_id={self.device_id!r}, name={self.name!r})"


from app.models.user import User  # noqa: E402,F401
