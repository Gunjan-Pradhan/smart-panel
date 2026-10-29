"""Migrations must build the expected schema and be reversible."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, pool, text

from app.db.base import Base
from app.models import RefreshToken, User  # noqa: F401  (registers tables)
from tests.conftest import (
    TEST_CYCLE_DB_NAME,
    alembic_config,
    create_database,
    drop_database,
)


def test_alembic_is_at_head(engine) -> None:
    with engine.connect() as conn:
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()

    assert revision == "0004"


def test_timescaledb_extension_installed(engine) -> None:
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        ).scalar()

    assert version == "2.31.0"


def test_expected_tables_exist(engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert {
        "users",
        "refresh_tokens",
        "devices",
        "loads",
        "channels",
        "events",
        "commands",
        "schedules",
        "audit_log",
        "telemetry",
        "alembic_version",
    } <= tables


def test_model_metadata_matches_database(engine) -> None:
    """Guard against a model being added without a matching migration."""

    inspector = inspect(engine)
    database_tables = set(inspector.get_table_names()) - {"alembic_version"}

    assert set(Base.metadata.tables) == database_tables

    for table_name, table in Base.metadata.tables.items():
        database_columns = {c["name"] for c in inspector.get_columns(table_name)}
        model_columns = {c.name for c in table.columns}
        assert model_columns == database_columns, table_name


def test_email_index_is_unique_and_case_insensitive(engine) -> None:
    with engine.connect() as conn:
        definition = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = 'uq_users_email_lower'"
            )
        ).scalar()

    assert definition is not None
    assert "UNIQUE INDEX" in definition
    assert "lower(email)" in definition


def test_foreign_keys_have_expected_delete_actions(engine) -> None:
    refresh_fks = {
        fk["name"]: fk for fk in inspect(engine).get_foreign_keys("refresh_tokens")
    }

    user_fk = refresh_fks["fk_refresh_tokens_user_id_users"]
    assert user_fk["referred_table"] == "users"
    assert user_fk["options"].get("ondelete") == "CASCADE"

    self_fk = refresh_fks["fk_refresh_tokens_replaced_by_id_refresh_tokens"]
    assert self_fk["referred_table"] == "refresh_tokens"
    assert self_fk["options"].get("ondelete") == "SET NULL"


@pytest.mark.slow
def test_full_downgrade_and_upgrade_cycle() -> None:
    """upgrade -> downgrade base -> upgrade, on an isolated database."""

    create_database(TEST_CYCLE_DB_NAME)
    config = alembic_config(TEST_CYCLE_DB_NAME)

    try:
        command.upgrade(config, "head")

        cycle_engine = create_engine(
            config.attributes["sqlalchemy_url"],
            poolclass=pool.NullPool,
        )
        try:
            assert "users" in inspect(cycle_engine).get_table_names()

            command.downgrade(config, "base")
            remaining = set(inspect(cycle_engine).get_table_names())
            assert "users" not in remaining
            assert "refresh_tokens" not in remaining

            command.upgrade(config, "head")
            assert "users" in inspect(cycle_engine).get_table_names()
        finally:
            cycle_engine.dispose()
    finally:
        drop_database(TEST_CYCLE_DB_NAME)
