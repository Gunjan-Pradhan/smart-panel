"""Migration 0008: multi-user device sharing and device_members table.

Schema reference: Workstream 6 - Multi-User Accounts, Sharing & Roles.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("device_id", "user_id", name="uq_device_members_device_user"),
        sa.CheckConstraint("role IN ('admin', 'viewer')", name="device_member_role_allowed"),
    )
    op.create_index("ix_device_members_device_id", "device_members", ["device_id"])
    op.create_index("ix_device_members_user_id", "device_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_device_members_user_id", table_name="device_members")
    op.drop_index("ix_device_members_device_id", table_name="device_members")
    op.drop_table("device_members")

