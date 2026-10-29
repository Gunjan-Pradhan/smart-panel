"""Opaque refresh tokens, stored hashed and rotated on every use.

Schema reference: docs/database_schema.md §4.2.

Notes:
- Only the SHA-256 hex digest is stored; the raw token is returned to the
  client once and never persisted.
- family_id groups a rotation chain so reuse can revoke every descendant.
- replaced_by_id uses ON DELETE SET NULL (the design document leaves the
  delete action open). This keeps a self-referencing chain from blocking the
  cascade when a user is deleted.
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # psycopg returns inet columns as ipaddress objects, not strings.
    ip_address: Mapped[
        ipaddress.IPv4Address | ipaddress.IPv6Address | None
    ] = mapped_column(INET, nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        CheckConstraint(
            "expires_at > issued_at",
            name="expiry_after_issue",
        ),
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="token_hash_hex",
        ),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"RefreshToken(id={self.id!r}, user_id={self.user_id!r})"


# Imported last to avoid a circular import at module load time.
from app.models.user import User  # noqa: E402,F401
