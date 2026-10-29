"""Electrical telemetry (TimescaleDB hypertable).

Schema reference: docs/database_schema.md §4.7.

The table is created by migration 0004 and converted into a hypertable there.
The composite primary key includes the partitioning column ``ts``, as
TimescaleDB requires.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
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
    from app.models.load import Load


class Telemetry(Base):
    __tablename__ = "telemetry"

    device_pk: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    ch: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    boot_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    v: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    i: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    p: Mapped[Decimal] = mapped_column(Numeric(9, 2), nullable=False)
    e_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    pf: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    f: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    relay: Mapped[bool] = mapped_column(Boolean, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    buffered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    clock_synced: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    load_pk: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("loads.id", ondelete="SET NULL"),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    device: Mapped["Device"] = relationship(back_populates="telemetry")
    load: Mapped["Load | None"] = relationship()

    __table_args__ = (
        PrimaryKeyConstraint("device_pk", "ch", "ts", name="pk_telemetry"),
        CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        CheckConstraint(
            "state IN ('OFF', 'STARTING', 'RUNNING', 'TRIPPED', "
            "'RETRY_WAIT', 'LOCKED_OUT', 'METER_FAULT')",
            name="state_allowed",
        ),
        CheckConstraint("pf >= 0 AND pf <= 1", name="pf_range"),
        CheckConstraint("v >= 0 AND i >= 0 AND p >= 0", name="measurements_non_negative"),
        Index(
            "ix_telemetry_device_pk_ch_ts",
            "device_pk",
            "ch",
            text("ts DESC"),
        ),
        Index("ix_telemetry_received_at", "received_at"),
    )
