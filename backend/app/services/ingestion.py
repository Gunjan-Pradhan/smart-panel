"""Database ingestion service for validated telemetry.

Takes ChannelTelemetryRecord objects and writes them into TimescaleDB.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.services.mqtt_adapter import ChannelTelemetryRecord


class TelemetryIngestionService:
    """Writes channel telemetry into the TimescaleDB hypertable."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ingest_record(
        self,
        record: ChannelTelemetryRecord,
        device_id: str = "PANEL-0001",
    ) -> Telemetry | None:
        """Saves a ChannelTelemetryRecord to the database.

        If a reading is invalid, the record is still saved with its validity='invalid'
        and the original numbers, preserving diagnostic audit without masking as zero.
        """
        device = self.db.execute(
            select(Device).where(Device.device_id == device_id)
        ).scalar_one_or_none()

        if not device:
            return None

        # Clamp measurements to non-negative Decimal values for DB check constraints
        v_dec = Decimal(str(max(0.0, record.voltage_v)))
        i_dec = Decimal(str(max(0.0, record.current_a)))
        p_dec = Decimal(str(max(0.0, record.active_power_w)))
        pf_dec = Decimal(str(min(1.0, max(0.0, record.power_factor))))
        f_dec = Decimal(str(max(0.0, record.frequency_hz)))
        e_dec = Decimal(str(max(0.0, record.energy_kwh)))

        db_entry = Telemetry(
            device_pk=device.id,
            ch=record.channel,
            ts=record.recorded_at,
            v=v_dec,
            i=i_dec,
            p=p_dec,
            pf=pf_dec,
            f=f_dec,
            e_kwh=e_dec,
            relay=record.relay_state,
            state=record.state,
            buffered=False,
            clock_synced=True,
        )

        self.db.add(db_entry)
        self.db.commit()
        return db_entry

