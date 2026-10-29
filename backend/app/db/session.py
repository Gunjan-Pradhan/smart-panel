"""Engine and session factory.

The engine is created lazily by SQLAlchemy: importing this module does not open
a connection, so tests can import models without a running database.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url(),
    pool_pre_ping=True,
    future=True,
    # Fail fast instead of hanging forever if the database is unreachable.
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""

    with SessionLocal() as session:
        yield session
