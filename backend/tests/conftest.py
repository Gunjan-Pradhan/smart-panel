"""Shared test fixtures.

Every test runs against a throwaway database (``smart_panel_test``) created on
the same PostgreSQL server used for development. The development database
``smart_panel`` is never modified.

Requirements:
- the Compose ``db`` service is running and healthy;
- the configured database user may CREATE DATABASE (it is the container
  superuser in local development).
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "smart_panel_test"
TEST_CYCLE_DB_NAME = "smart_panel_test_cycle"


def connect(database: str = "postgres", *, autocommit: bool = False):
    """psycopg connection built from settings.

    Keyword arguments are used deliberately: a URL string would risk the
    password appearing in an exception message.
    """

    settings = get_settings()
    return psycopg.connect(
        host=settings.database_host,
        port=settings.database_port,
        dbname=database,
        user=settings.database_user,
        password=settings.database_password.get_secret_value(),
        connect_timeout=10,
        autocommit=autocommit,
    )


def alembic_config(database: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["sqlalchemy_url"] = get_settings().database_url(database)
    return config


def create_database(name: str) -> None:
    drop_database(name)
    with connect(autocommit=True) as conn:
        # Identifier cannot be parameterised; the value is a module constant.
        conn.execute(f'CREATE DATABASE "{name}"')


def drop_database(name: str) -> None:
    with connect(autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


@pytest.fixture(scope="session")
def test_database_url() -> str:
    create_database(TEST_DB_NAME)
    command.upgrade(alembic_config(TEST_DB_NAME), "head")

    yield get_settings().database_url(TEST_DB_NAME).render_as_string(
        hide_password=False
    )

    drop_database(TEST_DB_NAME)


@pytest.fixture(scope="session")
def engine(test_database_url: str):
    engine = create_engine(test_database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(engine):
    """Session bound to the test database; tables are emptied after each test."""

    with Session(engine) as session:
        yield session

    # The session is closed (and its transaction rolled back) before cleanup,
    # so no locks are held by the time TRUNCATE runs.
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE audit_log, schedules, commands, events, "
                "telemetry, channels, loads, devices, refresh_tokens, users "
                "RESTART IDENTITY CASCADE"
            )
        )
