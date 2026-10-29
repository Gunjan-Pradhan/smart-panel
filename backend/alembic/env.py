"""Alembic environment.

The URL always comes from application settings (.env), never from alembic.ini.
Tests inject a URL through config.attributes["sqlalchemy_url"] so they can
target a throwaway database without mutating the environment.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Hide objects created by TimescaleDB itself from autogenerate.

    ``create_hypertable`` creates ``telemetry_ts_idx`` automatically. It is an
    implementation detail of the extension, not part of our logical schema, so
    it must not appear as a pending migration.
    """

    if type_ == "index" and name == "telemetry_ts_idx":
        return False
    return True


def _get_url():
    url = config.attributes.get("sqlalchemy_url")
    if url is None:
        url = get_settings().database_url()
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""

    context.configure(
        url=_get_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        _get_url(),
        poolclass=pool.NullPool,
        # Fail fast instead of hanging forever if the database is unreachable.
        connect_args={"connect_timeout": 10},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
