"""Tests for load profiles, fingerprints, learning sessions, and AI suggestion schema."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Channel,
    Device,
    LearningSession,
    LoadModeSelection,
    LoadProfile,
    ModeSuggestion,
    ProfileFingerprint,
    RecognitionEvent,
    User,
)

FAKE_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZmFrZWhhc2g"


def make_user(email="owner@example.com") -> User:
    return User(email=email, password_hash=FAKE_ARGON2)


def make_device(owner: User, device_id="PANEL-0001") -> Device:
    return Device(owner_id=owner.id, device_id=device_id, name="Test Panel")


def make_load_profile(owner: User, name="Provisional 125W Motor") -> LoadProfile:
    return LoadProfile(
        owner_id=owner.id,
        display_name=name,
        channel_last_seen=1,
        nominal_power_w=125.0,
        nominal_current_a=0.95,
    )


def make_learning_session(channel=1) -> LearningSession:
    return LearningSession(
        channel=channel,
        status="ready",
        valid_count=250,
        excluded_count=5,
        exclusion_reasons={"comm_error": 5},
        sampling_interval_s=1.0,
        feature_set_version="1.0.0",
        is_simulated=True,
    )


def make_fingerprint(
    profile: LoadProfile, session: LearningSession
) -> ProfileFingerprint:
    return ProfileFingerprint(
        profile_id=profile.id,
        learning_session_id=session.id,
        voltage_mean=230.1,
        voltage_std=1.2,
        current_mean=0.92,
        current_std=0.04,
        current_min=0.85,
        current_max=1.45,
        active_power_mean=124.5,
        active_power_std=4.5,
        active_power_min=110.0,
        active_power_max=135.0,
        power_factor_mean=0.68,
        power_factor_std=0.03,
        frequency_mean=50.01,
        frequency_std=0.05,
        apparent_power_s=211.7,
        reactive_power_q=171.3,
        reactive_ratio_q_s=0.81,
        cv_power=0.036,
        power_per_volt_sq=0.00235,
        startup_ratio=1.58,
        transition_count=0,
        feature_set_version="1.0.0",
        approved=True,
    )


def test_load_profile_crud_and_owner_cascade(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    profile = make_load_profile(user)
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    assert isinstance(profile.id, uuid.UUID)
    assert profile.display_name == "Provisional 125W Motor"
    assert profile.user_confirmed is False

    # Cascade on user deletion
    db_session.delete(user)
    db_session.commit()
    assert db_session.execute(select(LoadProfile)).scalars().all() == []


def test_learning_session_invariants(db_session) -> None:
    session = make_learning_session(channel=1)
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assert session.status == "ready"
    assert session.is_simulated is True

    # Invalid channel must be rejected
    with pytest.raises(IntegrityError):
        bad_session = make_learning_session(channel=3)
        db_session.add(bad_session)
        db_session.commit()
    db_session.rollback()

    # Invalid status must be rejected
    with pytest.raises(IntegrityError):
        bad_session = make_learning_session(channel=1)
        bad_session.status = "bad_status"
        db_session.add(bad_session)
        db_session.commit()
    db_session.rollback()


def test_profile_fingerprint_cascade(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    profile = make_load_profile(user)
    session = make_learning_session()
    db_session.add_all([profile, session])
    db_session.flush()

    fp = make_fingerprint(profile, session)
    db_session.add(fp)
    db_session.commit()

    # Deleting profile deletes fingerprint
    db_session.delete(profile)
    db_session.commit()

    assert db_session.execute(select(ProfileFingerprint)).scalars().all() == []
    # But learning session survives
    assert db_session.execute(select(LearningSession)).scalars().all() != []


def test_recognition_event_similarity_score_bounds(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    profile = make_load_profile(user)
    db_session.add(profile)
    db_session.flush()

    # Valid event
    event = RecognitionEvent(
        channel=1,
        best_candidate_id=profile.id,
        similarity_score=94.5,
        state="recognized",
    )
    db_session.add(event)
    db_session.commit()

    # Score > 100 must be rejected
    with pytest.raises(IntegrityError):
        bad_event = RecognitionEvent(
            channel=1,
            best_candidate_id=profile.id,
            similarity_score=105.0,
            state="recognized",
        )
        db_session.add(bad_event)
        db_session.commit()
    db_session.rollback()


def test_mode_suggestions_and_selections(db_session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()

    profile = make_load_profile(user)
    session = make_learning_session()
    db_session.add_all([profile, session])
    db_session.flush()

    suggestion = ModeSuggestion(
        learning_session_id=session.id,
        mode_name="power_factor_alert",
        rule_id="RULE_LOW_PF",
        reason_text="PF 0.68 is inductive. Power factor alert recommended.",
        triggering_values={"pf_mean": 0.68, "q_s_ratio": 0.81},
    )
    db_session.add(suggestion)
    db_session.commit()

    selection = LoadModeSelection(
        profile_id=profile.id,
        mode_name="power_factor_alert",
        enabled=True,
        source="ai_suggestion",
        selected_by=user.id,
    )
    db_session.add(selection)
    db_session.commit()

    # Duplicate selection for same profile & mode must fail
    with pytest.raises(IntegrityError):
        duplicate_selection = LoadModeSelection(
            profile_id=profile.id,
            mode_name="power_factor_alert",
            enabled=False,
            source="manual",
        )
        db_session.add(duplicate_selection)
        db_session.commit()
    db_session.rollback()


def test_unconfirmed_channel_invariant(db_session) -> None:
    """Verifies that newly created channels have empty limits and NULL confirmation."""
    user = make_user()
    db_session.add(user)
    db_session.flush()

    device = make_device(user)
    db_session.add(device)
    db_session.flush()

    channel = Channel(
        device_pk=device.id,
        ch=1,
        name="Channel 1 (Motor)",
    )
    db_session.add(channel)
    db_session.commit()
    db_session.refresh(channel)

    # Invariants mandated by safety prompt:
    assert channel.limits_confirmed_at is None
    assert channel.limits_confirmed_by is None
    assert channel.limit_current_a is None
    assert channel.limit_power_w is None
    assert channel.limit_voltage_min_v is None
    assert channel.limit_voltage_max_v is None
