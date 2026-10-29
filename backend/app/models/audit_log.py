"""Audit log for security-relevant actions.

Schema reference: docs/database_schema.md §4.11.
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[
        ipaddress.IPv4Address | ipaddress.IPv6Address | None
    ] = mapped_column(INET, nullable=True)

    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_audit_log_ts", text("ts DESC")),
        Index("ix_audit_log_user_id_ts", "user_id", text("ts DESC")),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"AuditLog(id={self.id!r}, action={self.action!r})"
