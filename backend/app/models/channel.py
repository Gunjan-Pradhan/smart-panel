"""Device channels (exactly two per device in this project).

Schema reference: docs/database_schema.md §4.4.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.device import Device
    from app.models.load import Load
    from app.models.user import User

CHANNEL_STATES = (
    "OFF",
    "STARTING",
    "RUNNING",
    "TRIPPED",
    "RETRY_WAIT",
    "LOCKED_OUT",
    "METER_FAULT",
)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    device_pk: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    ch: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    load_pk: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("loads.id", ondelete="SET NULL"),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'OFF'"),
    )
    relay_commanded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    last_telemetry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rated_voltage_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    rated_current_a: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 3), nullable=True
    )
    rated_power_w: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )

    limit_voltage_min_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    limit_voltage_max_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    limit_current_a: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 3), nullable=True
    )
    limit_power_w: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )
    limit_freq_min_hz: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    limit_freq_max_hz: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    limit_pf_min: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )

    startup_blanking_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    retry_delay_s: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("30"),
    )
    max_retries: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("3"),
    )

    limits_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    limits_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    device: Mapped["Device"] = relationship(back_populates="channels")
    load: Mapped["Load | None"] = relationship(back_populates="channels")
    confirmed_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[limits_confirmed_by]
    )

    __table_args__ = (
        UniqueConstraint("device_pk", "ch", name="uq_channels_device_pk_ch"),
        CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        CheckConstraint(
            "state IN ('OFF', 'STARTING', 'RUNNING', 'TRIPPED', "
            "'RETRY_WAIT', 'LOCKED_OUT', 'METER_FAULT')",
            name="state_allowed",
        ),
        CheckConstraint(
            "rated_voltage_v IS NULL OR rated_voltage_v >= 0",
            name="rated_voltage_non_negative",
        ),
        CheckConstraint(
            "rated_current_a IS NULL OR rated_current_a >= 0",
            name="rated_current_non_negative",
        ),
        CheckConstraint(
            "rated_power_w IS NULL OR rated_power_w >= 0",
            name="rated_power_non_negative",
        ),
        CheckConstraint(
            "limit_voltage_min_v IS NULL OR limit_voltage_min_v > 0",
            name="limit_voltage_min_positive",
        ),
        CheckConstraint(
            "limit_voltage_max_v IS NULL OR limit_voltage_max_v > 0",
            name="limit_voltage_max_positive",
        ),
        CheckConstraint(
            "limit_voltage_min_v IS NULL OR limit_voltage_max_v IS NULL "
            "OR limit_voltage_min_v < limit_voltage_max_v",
            name="limit_voltage_min_lt_max",
        ),
        CheckConstraint(
            "limit_current_a IS NULL OR limit_current_a > 0",
            name="limit_current_positive",
        ),
        CheckConstraint(
            "limit_power_w IS NULL OR limit_power_w > 0",
            name="limit_power_positive",
        ),
        CheckConstraint(
            "limit_freq_min_hz IS NULL OR limit_freq_min_hz > 0",
            name="limit_freq_min_positive",
        ),
        CheckConstraint(
            "limit_freq_max_hz IS NULL OR limit_freq_max_hz > 0",
            name="limit_freq_max_positive",
        ),
        CheckConstraint(
            "limit_freq_min_hz IS NULL OR limit_freq_max_hz IS NULL "
            "OR limit_freq_min_hz < limit_freq_max_hz",
            name="limit_freq_min_lt_max",
        ),
        CheckConstraint(
            "limit_pf_min IS NULL OR (limit_pf_min >= 0 AND limit_pf_min <= 1)",
            name="limit_pf_range",
        ),
        CheckConstraint(
            "startup_blanking_ms IS NULL OR "
            "(startup_blanking_ms >= 0 AND startup_blanking_ms <= 60000)",
            name="startup_blanking_range",
        ),
        CheckConstraint("retry_delay_s > 0", name="retry_delay_positive"),
        CheckConstraint(
            "max_retries BETWEEN 1 AND 10",
            name="max_retries_range",
        ),
        Index("ix_channels_device_pk", "device_pk"),
        Index("ix_channels_load_pk", "load_pk"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Channel(device_pk={self.device_pk!r}, ch={self.ch!r})"
