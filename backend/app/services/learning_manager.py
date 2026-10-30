"""Learning session manager state machine and profile repository.

Implements Section 3.2 of the build specification:
- Tracks session lifecycle (learning -> ready | unstable | insufficient_data | cancelled)
- Evaluates data quality fraction (>= 80% valid default)
- Evaluates stability (rejects wild power oscillations)
- Automatically calculates and persists fingerprints upon ready state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.load_profile import (
    LearningSession,
    LoadProfile,
    ProfileFingerprint,
)
from app.models.user import User
from app.services.fingerprint import ReadingSample, extract_fingerprint
from app.services.mode_suggester import ModeSuggester

MIN_VALID_FRACTION_DEFAULT = 0.80
MIN_READINGS_COUNT_DEFAULT = 15  # Scalable for testing; default in production is 200
MAX_CV_POWER_STABILITY = 0.35   # Maximum coefficient of variation allowed for "steady" load


class LearningSessionManager:
    """Manages active multi-minute learning sessions on a channel."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def start_session(
        self,
        channel: int,
        is_simulated: bool = False,
    ) -> LearningSession:
        """Starts a new learning session on the specified channel."""
        # Cancel any active session on this channel
        active_session = self.get_active_session(channel)
        if active_session:
            active_session.status = "cancelled"
            active_session.end_time = datetime.now(timezone.utc)
            self.db.commit()

        session = LearningSession(
            channel=channel,
            status="learning",
            valid_count=0,
            excluded_count=0,
            feature_set_version="1.0.0",
            is_simulated=is_simulated,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_active_session(self, channel: int) -> LearningSession | None:
        """Returns the currently running session on a channel if one exists."""
        stmt = (
            select(LearningSession)
            .where(
                LearningSession.channel == channel,
                LearningSession.status == "learning",
            )
            .order_by(LearningSession.start_time.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def cancel_session(self, session_id: uuid.UUID) -> LearningSession | None:
        """Cancels a session by ID."""
        session = self.db.get(LearningSession, session_id)
        if not session or session.status != "learning":
            return session
        session.status = "cancelled"
        session.end_time = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(session)
        return session

    def process_and_finalize_session(
        self,
        session_id: uuid.UUID,
        valid_samples: Sequence[ReadingSample],
        excluded_count: int = 0,
        exclusion_reasons: dict[str, int] | None = None,
        profile_owner: User | None = None,
        profile_name: str = "Learned Load",
        min_readings: int = MIN_READINGS_COUNT_DEFAULT,
        min_valid_fraction: float = MIN_VALID_FRACTION_DEFAULT,
    ) -> tuple[LearningSession, LoadProfile | None]:
        """Finalizes a learning session by evaluating data quality, stability, and extracting features."""
        session = self.db.get(LearningSession, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        total_samples = len(valid_samples) + excluded_count
        valid_fraction = (len(valid_samples) / total_samples) if total_samples > 0 else 0.0

        session.valid_count = len(valid_samples)
        session.excluded_count = excluded_count
        session.exclusion_reasons = exclusion_reasons or {}
        session.end_time = datetime.now(timezone.utc)

        # 1. Check for insufficient data
        if len(valid_samples) < min_readings or valid_fraction < min_valid_fraction:
            session.status = "insufficient_data"
            self.db.commit()
            return session, None

        # 2. Extract features to evaluate stability
        try:
            fp_data = extract_fingerprint(valid_samples)
        except ValueError:
            session.status = "insufficient_data"
            self.db.commit()
            return session, None

        # 3. Check for unstable load behaviour during window
        if fp_data.cv_power > MAX_CV_POWER_STABILITY:
            session.status = "unstable"
            self.db.commit()
            return session, None

        # 4. Success -> Mark ready and persist load profile + fingerprint
        session.status = "ready"

        profile: LoadProfile | None = None
        if profile_owner:
            profile = LoadProfile(
                owner_id=profile_owner.id,
                display_name=profile_name,
                channel_last_seen=session.channel,
                nominal_power_w=round(fp_data.active_power_mean, 2),
                nominal_current_a=round(fp_data.current_mean, 3),
                user_confirmed=False,
            )
            self.db.add(profile)
            self.db.flush()

            fp_record = ProfileFingerprint(
                profile_id=profile.id,
                learning_session_id=session.id,
                voltage_mean=fp_data.voltage_mean,
                voltage_std=fp_data.voltage_std,
                current_mean=fp_data.current_mean,
                current_std=fp_data.current_std,
                current_min=fp_data.current_min,
                current_max=fp_data.current_max,
                active_power_mean=fp_data.active_power_mean,
                active_power_std=fp_data.active_power_std,
                active_power_min=fp_data.active_power_min,
                active_power_max=fp_data.active_power_max,
                power_factor_mean=fp_data.power_factor_mean,
                power_factor_std=fp_data.power_factor_std,
                frequency_mean=fp_data.frequency_mean,
                frequency_std=fp_data.frequency_std,
                apparent_power_s=fp_data.apparent_power_s,
                reactive_power_q=fp_data.reactive_power_q,
                reactive_ratio_q_s=fp_data.reactive_ratio_q_s,
                cv_power=fp_data.cv_power,
                power_per_volt_sq=fp_data.power_per_volt_sq,
                startup_ratio=fp_data.startup_ratio,
                transition_count=fp_data.transition_count,
                feature_set_version=fp_data.feature_set_version,
                approved=False,
            )
            self.db.add(fp_record)
            self.db.flush()

            # Automatically evaluate rules and generate mode suggestions
            suggester = ModeSuggester(self.db)
            suggester.generate_suggestions(session.id, fp_record)

        self.db.commit()
        self.db.refresh(session)
        if profile:
            self.db.refresh(profile)
        return session, profile

