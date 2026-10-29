"""Constraint tests for users and refresh_tokens.

These tests prove the database itself rejects bad data, not just the ORM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import RefreshToken, User

VALID_HASH = "a" * 64
FAKE_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZmFrZWhhc2g"


def make_user(**overrides) -> User:
    data = {
        "email": "operator@example.com",
        "password_hash": FAKE_ARGON2,
    }
    data.update(overrides)
    return User(**data)


def make_token(user: User, **overrides) -> RefreshToken:
    now = datetime.now(timezone.utc)
    data = {
        "user_id": user.id,
        "token_hash": VALID_HASH,
        "family_id": uuid.uuid4(),
        "issued_at": now,
        "expires_at": now + timedelta(days=14),
    }
    data.update(overrides)
    return RefreshToken(**data)


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------


def test_user_defaults_are_applied_by_the_database(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert isinstance(user.id, uuid.UUID)
    assert user.role == "viewer"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.last_login_at is None


def test_duplicate_email_is_rejected(db_session) -> None:
    db_session.add(make_user(email="dup@example.com"))
    db_session.commit()

    db_session.add(make_user(email="dup@example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_uppercase_email_is_rejected(db_session) -> None:
    db_session.add(make_user(email="Mixed@Example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invalid_role_is_rejected(db_session) -> None:
    db_session.add(make_user(role="superuser"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_password_hash_is_required(db_session) -> None:
    db_session.add(make_user(password_hash=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# refresh_tokens
# --------------------------------------------------------------------------


def test_refresh_token_round_trip(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    token = make_token(user, ip_address="127.0.0.1")
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)

    assert token.token_hash == VALID_HASH
    # psycopg maps PostgreSQL inet to ipaddress.IPv4Address/IPv6Address.
    assert str(token.ip_address) == "127.0.0.1"
    assert token.revoked_at is None


def test_duplicate_token_hash_is_rejected(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.add(make_token(user))
    db_session.commit()

    db_session.add(make_token(user, family_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_non_hex_token_hash_is_rejected(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    db_session.add(make_token(user, token_hash="z" * 64))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_expiry_must_be_after_issue(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(
        make_token(user, issued_at=now, expires_at=now - timedelta(seconds=1))
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_user_cascades_to_refresh_tokens(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.add(make_token(user))
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    remaining = db_session.execute(select(RefreshToken)).scalars().all()
    assert remaining == []


def test_rotation_chain_survives_deleting_the_previous_token(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    first = make_token(user)
    db_session.add(first)
    db_session.flush()

    second = make_token(user, token_hash="b" * 64, replaced_by_id=first.id)
    db_session.add(second)
    db_session.commit()

    db_session.delete(first)
    db_session.commit()
    db_session.refresh(second)

    assert second.replaced_by_id is None
