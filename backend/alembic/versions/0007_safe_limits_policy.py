"""Migration 0007: safe limits policy, limit proposals, operator confirmation, and hard cap clamping.

Schema reference: Workstream 3 - Safe Limits Policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add proposed and confirmed limit columns to load_profiles
    op.add_column("load_profiles", sa.Column("proposed_current_limit_a", sa.Numeric(7, 3), nullable=True))
    op.add_column("load_profiles", sa.Column("proposed_power_limit_w", sa.Numeric(9, 2), nullable=True))
    op.add_column("load_profiles", sa.Column("proposed_voltage_min_v", sa.Numeric(7, 2), nullable=True))
    op.add_column("load_profiles", sa.Column("proposed_voltage_max_v", sa.Numeric(7, 2), nullable=True))
    op.add_column("load_profiles", sa.Column("proposed_inrush_blanking_ms", sa.Integer(), nullable=True))

    op.add_column(
        "load_profiles",
        sa.Column(
            "limits_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'NONE'"),
        ),
    )

    op.add_column("load_profiles", sa.Column("confirmed_current_limit_a", sa.Numeric(7, 3), nullable=True))
    op.add_column("load_profiles", sa.Column("confirmed_power_limit_w", sa.Numeric(9, 2), nullable=True))
    op.add_column("load_profiles", sa.Column("confirmed_voltage_min_v", sa.Numeric(7, 2), nullable=True))
    op.add_column("load_profiles", sa.Column("confirmed_voltage_max_v", sa.Numeric(7, 2), nullable=True))
    op.add_column("load_profiles", sa.Column("confirmed_inrush_blanking_ms", sa.Integer(), nullable=True))

    op.add_column(
        "load_profiles",
        sa.Column(
            "limits_confirmed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "load_profiles",
        sa.Column(
            "limits_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_load_profiles_limits_confirmed_by_users",
        "load_profiles",
        "users",
        ["limits_confirmed_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_check_constraint(
        "limits_status_allowed",
        "load_profiles",
        "limits_status IN ('NONE', 'PROPOSED', 'CONFIRMED', 'REJECTED')",
    )


def downgrade() -> None:
    op.drop_constraint("limits_status_allowed", "load_profiles", type_="check")
    op.drop_constraint("fk_load_profiles_limits_confirmed_by_users", "load_profiles", type_="foreignkey")

    op.drop_column("load_profiles", "limits_confirmed_at")
    op.drop_column("load_profiles", "limits_confirmed_by")
    op.drop_column("load_profiles", "confirmed_inrush_blanking_ms")
    op.drop_column("load_profiles", "confirmed_voltage_max_v")
    op.drop_column("load_profiles", "confirmed_voltage_min_v")
    op.drop_column("load_profiles", "confirmed_power_limit_w")
    op.drop_column("load_profiles", "confirmed_current_limit_a")
    op.drop_column("load_profiles", "limits_status")
    op.drop_column("load_profiles", "proposed_inrush_blanking_ms")
    op.drop_column("load_profiles", "proposed_voltage_max_v")
    op.drop_column("load_profiles", "proposed_voltage_min_v")
    op.drop_column("load_profiles", "proposed_power_limit_w")
    op.drop_column("load_profiles", "proposed_current_limit_a")

