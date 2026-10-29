"""Schedules (backend evaluation in Phase 6).

Schema reference: docs/database_schema.md §4.10.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.device import Device
    from app.models.user import User


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_pk: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    ch: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    days_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    on_time: Mapped[time] = mapped_column(Time, nullable=False)
    off_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
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

    owner: Mapped["User"] = relationship(back_populates="schedules")
    device: Mapped["Device"] = relationship(back_populates="schedules")

    __table_args__ = (
        CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        CheckConstraint(
            "days_of_week BETWEEN 1 AND 127",
            name="days_of_week_range",
        ),
        CheckConstraint("on_time <> off_time", name="times_differ"),
        Index("ix_schedules_owner_id", "owner_id"),
        Index("ix_schedules_device_pk", "device_pk"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Schedule(id={self.id!r}, name={self.name!r})"
