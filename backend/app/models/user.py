"""User accounts.

Schema reference: docs/database_schema.md §4.1.

Security notes:
- password_hash stores an Argon2id encoded hash, never a password.
- Emails are stored lower-case and unique case-insensitively (functional
  unique index on lower(email)).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.device import Device
    from app.models.load import Load
    from app.models.schedule import Schedule

# Allowed roles. Least privilege default is "viewer".
ROLES = ("admin", "operator", "viewer")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'viewer'"),
    )
    is_active: Mapped[bool] = mapped_column(
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
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    devices: Mapped[list["Device"]] = relationship(
        back_populates="owner",
        passive_deletes=True,
    )
    loads: Mapped[list["Load"]] = relationship(
        back_populates="owner",
        passive_deletes=True,
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'operator', 'viewer')",
            name="role_allowed",
        ),
        # Keeps the "stored lower-case" rule true even for raw SQL inserts.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # Case-insensitive uniqueness; the application also normalises input.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"User(id={self.id!r}, email={self.email!r}, role={self.role!r})"
