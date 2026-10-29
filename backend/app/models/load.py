"""Persistent load identities.

Schema reference: docs/database_schema.md §4.5.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.channel import Channel
    from app.models.user import User

LOAD_CODE_PATTERN = r"^LP-[0-9]{4}$"
LOAD_CATEGORIES = ("motor", "lighting", "heater", "other")


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    load_code: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    rated_voltage_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    rated_current_a: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 3), nullable=True
    )
    rated_power_w: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )
    rated_pf: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    owner: Mapped["User"] = relationship(back_populates="loads")
    channels: Mapped[list["Channel"]] = relationship(back_populates="load")

    __table_args__ = (
        UniqueConstraint("load_code", name="uq_loads_load_code"),
        CheckConstraint(
            f"load_code ~ '{LOAD_CODE_PATTERN}'",
            name="load_code_format",
        ),
        CheckConstraint(
            "category IN ('motor', 'lighting', 'heater', 'other')",
            name="category_allowed",
        ),
        CheckConstraint(
            "rated_pf IS NULL OR (rated_pf >= 0 AND rated_pf <= 1)",
            name="rated_pf_range",
        ),
        Index("ix_loads_owner_id", "owner_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Load(load_code={self.load_code!r}, name={self.name!r})"


from app.models.user import User  # noqa: E402,F401
