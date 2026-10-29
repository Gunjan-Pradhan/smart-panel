"""Migration 0001: enable required PostgreSQL extensions.

Schema reference: docs/database_schema.md §7 item 1.

TimescaleDB must be preloaded by the server (shared_preload_libraries).
Installing the extension is per-database, so this migration is what makes a
fresh database able to hold hypertables. It requires a superuser or a role
that has been granted the extension; in this project the Compose user is the
database owner.

pgcrypto is intentionally NOT enabled: UUIDs are generated in Python.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")


def downgrade() -> None:
    # Safe here because the telemetry migration is always downgraded first.
    op.execute("DROP EXTENSION IF EXISTS timescaledb")
