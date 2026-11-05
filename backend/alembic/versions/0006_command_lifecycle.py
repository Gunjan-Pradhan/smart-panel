"""Migration 0006: command lifecycle, sent status, execution tracking, and timeout support.

Schema reference: Workstream 4 - Remote Control with Real Ack.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to commands table
    op.add_column(
        "commands",
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "commands",
        sa.Column(
            "duration_seconds",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "commands",
        sa.Column(
            "priority",
            sa.Text(),
            nullable=True,
            server_default=sa.text("'user'"),
        ),
    )

    # 2. Update check constraints on commands table
    op.drop_constraint("status_allowed", "commands", type_="check")
    op.create_check_constraint(
        "status_allowed",
        "commands",
        "status IN ('PENDING', 'SENT', 'DONE', 'REJECTED', 'REFUSED', 'FAILED', 'TIMED_OUT', 'TIMEOUT')",
    )

    op.drop_constraint("pending_has_no_ack", "commands", type_="check")
    op.create_check_constraint(
        "pending_has_no_ack",
        "commands",
        "status NOT IN ('PENDING', 'SENT') OR acked_at IS NULL",
    )

    # 3. Add index for timeout scanner
    op.create_index(
        "ix_commands_active_status",
        "commands",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_commands_active_status", table_name="commands")

    op.drop_constraint("pending_has_no_ack", "commands", type_="check")
    op.create_check_constraint(
        "pending_has_no_ack",
        "commands",
        "status <> 'PENDING' OR acked_at IS NULL",
    )

    op.drop_constraint("status_allowed", "commands", type_="check")
    op.create_check_constraint(
        "status_allowed",
        "commands",
        "status IN ('PENDING', 'DONE', 'REJECTED', 'FAILED', 'TIMED_OUT')",
    )

    op.drop_column("commands", "priority")
    op.drop_column("commands", "duration_seconds")
    op.drop_column("commands", "executed_at")

