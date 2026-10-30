"""Load Recognition Engine.

Implements Section 3.3 of the build specification:
- Compares live telemetry observation windows against stored profile fingerprints
- Computes standardized weighted distance across physical electrical features (P, PF, Q, I, Q/S, CV_P)
- Converts distance to a normalized 0-100 similarity score
- Classifies match state: recognized, ambiguous, unknown, insufficient_data
- Records recognition events in PostgreSQL for audit and operator feedback
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.load_profile import (
    LoadProfile,
    ProfileFingerprint,
    RecognitionEvent,
)
from app.services.fingerprint import (
    ExtractedFingerprint,
    ReadingSample,
    extract_fingerprint,
)

MIN_RECOGNITION_SAMPLES = 10
RECOGNITION_THRESHOLD_HIGH = 80.0
RECOGNITION_THRESHOLD_MID = 60.0
AMBIGUITY_GAP_MIN = 15.0


@dataclass(frozen=True)
class CandidateMatch:
    profile: LoadProfile
    fingerprint: ProfileFingerprint
    similarity_score: float
    distance: float


@dataclass(frozen=True)
class RecognitionResult:
    state: str
    similarity_score: float
    best_candidate: LoadProfile | None
    runner_up: LoadProfile | None
    live_fingerprint: ExtractedFingerprint | None
    matches: list[CandidateMatch]


def compute_standardized_distance(
    live: ExtractedFingerprint,
    target: ProfileFingerprint,
) -> float:
    """Computes standardized weighted Euclidean distance between live and target fingerprints."""
    # 1. Active power delta
    p_scale = max(15.0, 0.15 * abs(target.active_power_mean))
    delta_p = (live.active_power_mean - target.active_power_mean) / p_scale

    # 2. Power factor delta
    delta_pf = (live.power_factor_mean - target.power_factor_mean) / 0.08

    # 3. Reactive power delta
    q_scale = max(12.0, 0.15 * abs(target.reactive_power_q))
    delta_q = (live.reactive_power_q - target.reactive_power_q) / q_scale

    # 4. Current delta
    i_scale = max(0.10, 0.15 * abs(target.current_mean))
    delta_i = (live.current_mean - target.current_mean) / i_scale

    # 5. Reactive ratio Q/S delta
    delta_qs = (live.reactive_ratio_q_s - target.reactive_ratio_q_s) / 0.10

    # 6. Power stability (CV) delta
    delta_cv = (live.cv_power - target.cv_power) / 0.15

    # Weighted quadratic sum
    # Weights sum to 1.00: P(0.28), PF(0.25), Q(0.18), I(0.14), Q/S(0.10), CV(0.05)
    sum_sq = (
        0.28 * (delta_p**2)
        + 0.25 * (delta_pf**2)
        + 0.18 * (delta_q**2)
        + 0.14 * (delta_i**2)
        + 0.10 * (delta_qs**2)
        + 0.05 * (delta_cv**2)
    )

    return math.sqrt(sum_sq)


def distance_to_similarity(distance: float) -> float:
    """Converts a standardized distance to a smooth 0-100 similarity score."""
    score = 100.0 * math.exp(-0.5 * distance)
    return round(max(0.0, min(100.0, score)), 2)


class RecognitionEngine:
    """Service that evaluates observation windows and manages recognition events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate_window(
        self,
        samples: Sequence[ReadingSample],
        candidates: Sequence[LoadProfile],
        min_samples: int = MIN_RECOGNITION_SAMPLES,
    ) -> RecognitionResult:
        """Evaluates an observation window against a candidate set of load profiles."""
        if len(samples) < min_samples:
            return RecognitionResult(
                state="insufficient_data",
                similarity_score=0.0,
                best_candidate=None,
                runner_up=None,
                live_fingerprint=None,
                matches=[],
            )

        try:
            live_fp = extract_fingerprint(samples)
        except ValueError:
            return RecognitionResult(
                state="insufficient_data",
                similarity_score=0.0,
                best_candidate=None,
                runner_up=None,
                live_fingerprint=None,
                matches=[],
            )

        # Evaluate against all candidate profiles that have at least one fingerprint
        matches: list[CandidateMatch] = []
        for profile in candidates:
            if not profile.fingerprints:
                continue
            # Compare with the most recent approved or latest fingerprint of this profile
            target_fp = profile.fingerprints[-1]
            dist = compute_standardized_distance(live_fp, target_fp)
            score = distance_to_similarity(dist)
            matches.append(
                CandidateMatch(
                    profile=profile,
                    fingerprint=target_fp,
                    similarity_score=score,
                    distance=dist,
                )
            )

        if not matches:
            return RecognitionResult(
                state="unknown",
                similarity_score=0.0,
                best_candidate=None,
                runner_up=None,
                live_fingerprint=live_fp,
                matches=[],
            )

        # Sort matches by similarity score descending
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        best = matches[0]
        runner_up = matches[1] if len(matches) > 1 else None

        best_score = best.similarity_score
        runner_up_score = runner_up.similarity_score if runner_up else 0.0

        # Classification decision rules
        if best_score >= RECOGNITION_THRESHOLD_HIGH:
            if runner_up and (best_score - runner_up_score < AMBIGUITY_GAP_MIN):
                state = "ambiguous"
            else:
                state = "recognized"
        elif best_score >= RECOGNITION_THRESHOLD_MID:
            state = "ambiguous"
        else:
            state = "unknown"

        return RecognitionResult(
            state=state,
            similarity_score=best_score,
            best_candidate=best.profile,
            runner_up=runner_up.profile if runner_up else None,
            live_fingerprint=live_fp,
            matches=matches,
        )

    def recognize_and_record(
        self,
        channel: int,
        owner_id: uuid.UUID,
        samples: Sequence[ReadingSample],
        min_samples: int = MIN_RECOGNITION_SAMPLES,
    ) -> RecognitionEvent:
        """Evaluates live samples against user-owned profiles and persists the RecognitionEvent."""
        # Query active candidate profiles owned by this user
        stmt = (
            select(LoadProfile)
            .where(
                LoadProfile.owner_id == owner_id,
                (LoadProfile.channel_last_seen == channel)
                | (LoadProfile.channel_last_seen.is_(None)),
            )
            .order_by(LoadProfile.created_at.desc())
        )
        candidates = list(self.db.execute(stmt).scalars().unique().all())

        # If no channel-specific profiles found, search all profiles owned by user
        if not candidates:
            stmt_all = (
                select(LoadProfile)
                .where(LoadProfile.owner_id == owner_id)
                .order_by(LoadProfile.created_at.desc())
            )
            candidates = list(self.db.execute(stmt_all).scalars().unique().all())

        result = self.evaluate_window(samples, candidates, min_samples=min_samples)

        event = RecognitionEvent(
            channel=channel,
            recognized_at=datetime.now(timezone.utc),
            best_candidate_id=result.best_candidate.id if result.best_candidate else None,
            similarity_score=result.similarity_score,
            runner_up_id=result.runner_up.id if result.runner_up else None,
            state=result.state,
            user_feedback="pending",
            corrected_profile_id=None,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def submit_feedback(
        self,
        event_id: uuid.UUID,
        user_feedback: str,
        corrected_profile_id: uuid.UUID | None = None,
    ) -> RecognitionEvent | None:
        """Records operator confirmation or correction on a past recognition event."""
        event = self.db.get(RecognitionEvent, event_id)
        if not event:
            return None

        event.user_feedback = user_feedback
        if user_feedback == "corrected" and corrected_profile_id:
            event.corrected_profile_id = corrected_profile_id

        self.db.commit()
        self.db.refresh(event)
        return event

