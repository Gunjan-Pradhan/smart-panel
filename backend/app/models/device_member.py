"""Device members (multi-user sharing and role assignment).

Schema reference: Workstream 6 - Multi-User Accounts, Sharing & Roles.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.device import Device
    from app.models.user import User


class DeviceMember(Base):
    __tablename__ = "device_members"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    device: Mapped["Device"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="device_memberships")

    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="uq_device_members_device_user"),
        CheckConstraint("role IN ('admin', 'viewer')", name="device_member_role_allowed"),
        Index("ix_device_members_device_id", "device_id"),
        Index("ix_device_members_user_id", "user_id"),
    )

