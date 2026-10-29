"""Device events (protection trips, communication faults, command rejections).

Schema reference: docs/database_schema.md §4.8.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.device import Device

EVENT_SEVERITIES = ("info", "warning", "critical")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    device_pk: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    ch: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    device: Mapped["Device"] = relationship(back_populates="events")

    __table_args__ = (
        CheckConstraint("ch IS NULL OR ch IN (1, 2)", name="ch_allowed"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="severity_allowed",
        ),
        Index("ix_events_device_pk_ts", "device_pk", text("ts DESC")),
        Index("ix_events_type", "type"),
        Index("ix_events_severity", "severity"),
    )
