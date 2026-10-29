"""Migration 0004: telemetry hypertable.

Schema reference: docs/database_schema.md §4.7 and §7 item 3.

The table is created first and then converted with ``create_hypertable``.
The composite primary key includes ``ts`` because TimescaleDB requires every
unique index on a hypertable to contain the partitioning column.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telemetry",
        sa.Column("device_pk", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ch", sa.SmallInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("boot_id", sa.Text(), nullable=True),
        sa.Column("seq", sa.BigInteger(), nullable=True),
        sa.Column("v", sa.Numeric(7, 2), nullable=False),
        sa.Column("i", sa.Numeric(7, 3), nullable=False),
        sa.Column("p", sa.Numeric(9, 2), nullable=False),
        sa.Column("e_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("pf", sa.Numeric(4, 3), nullable=False),
        sa.Column("f", sa.Numeric(5, 2), nullable=False),
        sa.Column("relay", sa.Boolean(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("buffered", sa.Boolean(), nullable=False),
        sa.Column("clock_synced", sa.Boolean(), nullable=True),
        sa.Column("load_pk", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        sa.CheckConstraint(
            "state IN ('OFF', 'STARTING', 'RUNNING', 'TRIPPED', "
            "'RETRY_WAIT', 'LOCKED_OUT', 'METER_FAULT')",
            name="state_allowed",
        ),
        sa.CheckConstraint("pf >= 0 AND pf <= 1", name="pf_range"),
        sa.CheckConstraint(
            "v >= 0 AND i >= 0 AND p >= 0",
            name="measurements_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["device_pk"],
            ["devices.id"],
            name="fk_telemetry_device_pk_devices",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["load_pk"],
            ["loads.id"],
            name="fk_telemetry_load_pk_loads",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("device_pk", "ch", "ts", name="pk_telemetry"),
    )

    op.execute(
        "SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE)"
    )

    op.create_index(
        "ix_telemetry_device_pk_ch_ts",
        "telemetry",
        ["device_pk", "ch", sa.text("ts DESC")],
    )
    op.create_index("ix_telemetry_received_at", "telemetry", ["received_at"])


def downgrade() -> None:
    # Dropping the table also removes its chunks.
    op.drop_table("telemetry")
