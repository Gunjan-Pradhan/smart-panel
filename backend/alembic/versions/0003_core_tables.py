"""Migration 0003: core tables.

Schema reference: docs/database_schema.md §4.3–4.6, §4.8–4.11.

Tables are created in dependency order. Constraint names are given in their
short form so the naming convention in app/db/base.py produces names such as
``ck_channels_ch_allowed`` exactly once.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mqtt_username", sa.Text(), nullable=True),
        sa.Column("fw_version", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "online",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "device_id ~ '^[A-Z0-9]{2,16}-[0-9]{4}$'",
            name="device_id_format",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_devices_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("device_id", name="uq_devices_device_id"),
        sa.UniqueConstraint("mqtt_username", name="uq_devices_mqtt_username"),
    )
    op.create_index("ix_devices_owner_id", "devices", ["owner_id"])
    op.create_index("ix_devices_last_seen_at", "devices", ["last_seen_at"])

    op.create_table(
        "loads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("load_code", sa.Text(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("rated_voltage_v", sa.Numeric(7, 2), nullable=True),
        sa.Column("rated_current_a", sa.Numeric(7, 3), nullable=True),
        sa.Column("rated_power_w", sa.Numeric(9, 2), nullable=True),
        sa.Column("rated_pf", sa.Numeric(4, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "load_code ~ '^LP-[0-9]{4}$'",
            name="load_code_format",
        ),
        sa.CheckConstraint(
            "category IN ('motor', 'lighting', 'heater', 'other')",
            name="category_allowed",
        ),
        sa.CheckConstraint(
            "rated_pf IS NULL OR (rated_pf >= 0 AND rated_pf <= 1)",
            name="rated_pf_range",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_loads_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_loads"),
        sa.UniqueConstraint("load_code", name="uq_loads_load_code"),
    )
    op.create_index("ix_loads_owner_id", "loads", ["owner_id"])

    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_pk", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ch", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("load_pk", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "state",
            sa.Text(),
            server_default=sa.text("'OFF'"),
            nullable=False,
        ),
        sa.Column(
            "relay_commanded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "last_telemetry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("rated_voltage_v", sa.Numeric(7, 2), nullable=True),
        sa.Column("rated_current_a", sa.Numeric(7, 3), nullable=True),
        sa.Column("rated_power_w", sa.Numeric(9, 2), nullable=True),
        sa.Column("limit_voltage_min_v", sa.Numeric(7, 2), nullable=True),
        sa.Column("limit_voltage_max_v", sa.Numeric(7, 2), nullable=True),
        sa.Column("limit_current_a", sa.Numeric(7, 3), nullable=True),
        sa.Column("limit_power_w", sa.Numeric(9, 2), nullable=True),
        sa.Column("limit_freq_min_hz", sa.Numeric(5, 2), nullable=True),
        sa.Column("limit_freq_max_hz", sa.Numeric(5, 2), nullable=True),
        sa.Column("limit_pf_min", sa.Numeric(4, 3), nullable=True),
        sa.Column("startup_blanking_ms", sa.Integer(), nullable=True),
        sa.Column(
            "retry_delay_s",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "max_retries",
            sa.SmallInteger(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column(
            "limits_confirmed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "limits_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
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
        sa.CheckConstraint(
            "rated_voltage_v IS NULL OR rated_voltage_v >= 0",
            name="rated_voltage_non_negative",
        ),
        sa.CheckConstraint(
            "rated_current_a IS NULL OR rated_current_a >= 0",
            name="rated_current_non_negative",
        ),
        sa.CheckConstraint(
            "rated_power_w IS NULL OR rated_power_w >= 0",
            name="rated_power_non_negative",
        ),
        sa.CheckConstraint(
            "limit_voltage_min_v IS NULL OR limit_voltage_min_v > 0",
            name="limit_voltage_min_positive",
        ),
        sa.CheckConstraint(
            "limit_voltage_max_v IS NULL OR limit_voltage_max_v > 0",
            name="limit_voltage_max_positive",
        ),
        sa.CheckConstraint(
            "limit_voltage_min_v IS NULL OR limit_voltage_max_v IS NULL "
            "OR limit_voltage_min_v < limit_voltage_max_v",
            name="limit_voltage_min_lt_max",
        ),
        sa.CheckConstraint(
            "limit_current_a IS NULL OR limit_current_a > 0",
            name="limit_current_positive",
        ),
        sa.CheckConstraint(
            "limit_power_w IS NULL OR limit_power_w > 0",
            name="limit_power_positive",
        ),
        sa.CheckConstraint(
            "limit_freq_min_hz IS NULL OR limit_freq_min_hz > 0",
            name="limit_freq_min_positive",
        ),
        sa.CheckConstraint(
            "limit_freq_max_hz IS NULL OR limit_freq_max_hz > 0",
            name="limit_freq_max_positive",
        ),
        sa.CheckConstraint(
            "limit_freq_min_hz IS NULL OR limit_freq_max_hz IS NULL "
            "OR limit_freq_min_hz < limit_freq_max_hz",
            name="limit_freq_min_lt_max",
        ),
        sa.CheckConstraint(
            "limit_pf_min IS NULL OR (limit_pf_min >= 0 AND limit_pf_min <= 1)",
            name="limit_pf_range",
        ),
        sa.CheckConstraint(
            "startup_blanking_ms IS NULL OR "
            "(startup_blanking_ms >= 0 AND startup_blanking_ms <= 60000)",
            name="startup_blanking_range",
        ),
        sa.CheckConstraint("retry_delay_s > 0", name="retry_delay_positive"),
        sa.CheckConstraint(
            "max_retries BETWEEN 1 AND 10",
            name="max_retries_range",
        ),
        sa.ForeignKeyConstraint(
            ["device_pk"],
            ["devices.id"],
            name="fk_channels_device_pk_devices",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["load_pk"],
            ["loads.id"],
            name="fk_channels_load_pk_loads",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["limits_confirmed_by"],
            ["users.id"],
            name="fk_channels_limits_confirmed_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channels"),
        sa.UniqueConstraint("device_pk", "ch", name="uq_channels_device_pk_ch"),
    )
    op.create_index("ix_channels_device_pk", "channels", ["device_pk"])
    op.create_index("ix_channels_load_pk", "channels", ["load_pk"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_pk", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ch", sa.SmallInteger(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ch IS NULL OR ch IN (1, 2)", name="ch_allowed"),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="severity_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["device_pk"],
            ["devices.id"],
            name="fk_events_device_pk_devices",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index(
        "ix_events_device_pk_ts",
        "events",
        ["device_pk", sa.text("ts DESC")],
    )
    op.create_index("ix_events_type", "events", ["type"])
    op.create_index("ix_events_severity", "events", ["severity"])

    op.create_table(
        "commands",
        sa.Column("cmd_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_pk", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ch", sa.SmallInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relay_after", sa.Boolean(), nullable=True),
        sa.Column("state_after", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        sa.CheckConstraint("action IN ('ON', 'OFF')", name="action_allowed"),
        sa.CheckConstraint(
            "source IN ('user', 'schedule', 'system', 'optimization')",
            name="source_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'DONE', 'REJECTED', 'FAILED', 'TIMED_OUT')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="expiry_after_issue",
        ),
        sa.CheckConstraint(
            "status <> 'PENDING' OR acked_at IS NULL",
            name="pending_has_no_ack",
        ),
        sa.ForeignKeyConstraint(
            ["device_pk"],
            ["devices.id"],
            name="fk_commands_device_pk_devices",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_commands_requested_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("cmd_id", name="pk_commands"),
    )
    op.create_index(
        "ix_commands_device_pk_issued_at",
        "commands",
        ["device_pk", sa.text("issued_at DESC")],
    )
    op.create_index(
        "ix_commands_pending",
        "commands",
        ["status"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_pk", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ch", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("days_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("on_time", sa.Time(), nullable=False),
        sa.Column("off_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ch IN (1, 2)", name="ch_allowed"),
        sa.CheckConstraint(
            "days_of_week BETWEEN 1 AND 127",
            name="days_of_week_range",
        ),
        sa.CheckConstraint("on_time <> off_time", name="times_differ"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_schedules_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_pk"],
            ["devices.id"],
            name="fk_schedules_device_pk_devices",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_schedules"),
    )
    op.create_index("ix_schedules_owner_id", "schedules", ["owner_id"])
    op.create_index("ix_schedules_device_pk", "schedules", ["device_pk"])

    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_audit_log_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_ts", "audit_log", [sa.text("ts DESC")])
    op.create_index(
        "ix_audit_log_user_id_ts",
        "audit_log",
        ["user_id", sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("schedules")
    op.drop_table("commands")
    op.drop_table("events")
    op.drop_table("channels")
    op.drop_table("loads")
    op.drop_table("devices")
