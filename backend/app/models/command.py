"""Relay commands issued to a device.

Schema reference: docs/database_schema.md §4.9.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.device import Device
    from app.models.user import User

COMMAND_ACTIONS = ("ON", "OFF")
COMMAND_SOURCES = ("user", "schedule", "system", "optimization")
COMMAND_STATUSES = ("PENDING", "DONE", "REJECTED", "FAILED", "TIMED_OUT")


class Command(Base):
    __tablename__ = "commands"

    cmd_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    device_pk: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    ch: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'PENDING'"),
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    relay_after: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    state_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    device: Mapped["Device"] = relationship(back_populates="commands")
    requested_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[requested_by]
    )

    __table_args__ = (
        CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        CheckConstraint("action IN ('ON', 'OFF')", name="action_allowed"),
        CheckConstraint(
            "source IN ('user', 'schedule', 'system', 'optimization')",
            name="source_allowed",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'DONE', 'REJECTED', 'FAILED', 'TIMED_OUT')",
            name="status_allowed",
        ),
        CheckConstraint("expires_at > issued_at", name="expiry_after_issue"),
        CheckConstraint(
            "status <> 'PENDING' OR acked_at IS NULL",
            name="pending_has_no_ack",
        ),
        Index(
            "ix_commands_device_pk_issued_at",
            "device_pk",
            text("issued_at DESC"),
        ),
        Index(
            "ix_commands_pending",
            "status",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Command(cmd_id={self.cmd_id!r}, action={self.action!r})"
