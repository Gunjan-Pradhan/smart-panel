"""Load profiles, learning sessions, fingerprints, recognition, and mode suggestions.

Schema reference: Section 3.7 of build specification.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User

LEARNING_SESSION_STATUSES = (
    "learning",
    "ready",
    "unstable",
    "insufficient_data",
    "cancelled",
)

RECOGNITION_STATES = (
    "recognized",
    "ambiguous",
    "unknown",
    "insufficient_data",
)

RECOGNITION_USER_FEEDBACK = (
    "pending",
    "confirmed",
    "corrected",
)

MODE_SELECTION_SOURCES = (
    "ai_suggestion",
    "manual",
    "saved_profile",
)


class LoadProfile(Base):
    """User-confirmed or learned profile of an electrical load."""

    __tablename__ = "load_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    channel_last_seen: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    nominal_power_w: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )
    nominal_current_a: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 3), nullable=True
    )
    # Proposed & Confirmed Safety Limits (Workstream 3)
    proposed_current_limit_a: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 3), nullable=True
    )
    proposed_power_limit_w: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )
    proposed_voltage_min_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    proposed_voltage_max_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    proposed_inrush_blanking_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    limits_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'NONE'")
    )
    confirmed_current_limit_a: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 3), nullable=True
    )
    confirmed_power_limit_w: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )
    confirmed_voltage_min_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    confirmed_voltage_max_v: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    confirmed_inrush_blanking_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    limits_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    limits_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])
    limits_confirmer: Mapped["User | None"] = relationship(foreign_keys=[limits_confirmed_by])
    fingerprints: Mapped[list["ProfileFingerprint"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    mode_selections: Mapped[list["LoadModeSelection"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "channel_last_seen IS NULL OR channel_last_seen IN (1, 2)",
            name="channel_last_seen_valid",
        ),
        Index("ix_load_profiles_owner_id", "owner_id"),
    )


class LearningSession(Base):
    """A multi-minute observation window for fingerprint extraction."""

    __tablename__ = "learning_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="learning")
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    exclusion_reasons: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    sampling_interval_s: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    feature_set_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="1.0.0"
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    fingerprints: Mapped[list["ProfileFingerprint"]] = relationship(
        back_populates="session"
    )
    suggestions: Mapped[list["ModeSuggestion"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("channel IN (1, 2)", name="channel_valid"),
        CheckConstraint(
            "status IN ('learning', 'ready', 'unstable', 'insufficient_data', 'cancelled')",
            name="status_valid",
        ),
        Index("ix_learning_sessions_channel_status", "channel", "status"),
    )


class ProfileFingerprint(Base):
    """Calculated electrical signature and statistical feature vector."""

    __tablename__ = "profile_fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("load_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    learning_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learning_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Statistical features
    voltage_mean: Mapped[float] = mapped_column(Float, nullable=False)
    voltage_std: Mapped[float] = mapped_column(Float, nullable=False)
    current_mean: Mapped[float] = mapped_column(Float, nullable=False)
    current_std: Mapped[float] = mapped_column(Float, nullable=False)
    current_min: Mapped[float] = mapped_column(Float, nullable=False)
    current_max: Mapped[float] = mapped_column(Float, nullable=False)
    active_power_mean: Mapped[float] = mapped_column(Float, nullable=False)
    active_power_std: Mapped[float] = mapped_column(Float, nullable=False)
    active_power_min: Mapped[float] = mapped_column(Float, nullable=False)
    active_power_max: Mapped[float] = mapped_column(Float, nullable=False)
    power_factor_mean: Mapped[float] = mapped_column(Float, nullable=False)
    power_factor_std: Mapped[float] = mapped_column(Float, nullable=False)
    frequency_mean: Mapped[float] = mapped_column(Float, nullable=False)
    frequency_std: Mapped[float] = mapped_column(Float, nullable=False)
    apparent_power_s: Mapped[float] = mapped_column(Float, nullable=False)
    reactive_power_q: Mapped[float] = mapped_column(Float, nullable=False)
    reactive_ratio_q_s: Mapped[float] = mapped_column(Float, nullable=False)
    cv_power: Mapped[float] = mapped_column(Float, nullable=False)
    power_per_volt_sq: Mapped[float] = mapped_column(Float, nullable=False)
    startup_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Metadata
    feature_set_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="1.0.0"
    )
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    profile: Mapped["LoadProfile"] = relationship(back_populates="fingerprints")
    session: Mapped["LearningSession | None"] = relationship(
        back_populates="fingerprints"
    )

    __table_args__ = (
        Index("ix_profile_fingerprints_profile_id", "profile_id"),
    )


class RecognitionEvent(Base):
    """Event logged when load behaviour is compared against saved profiles."""

    __tablename__ = "recognition_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    recognized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    best_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("load_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    runner_up_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("load_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    user_feedback: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )
    corrected_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("load_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    best_candidate: Mapped["LoadProfile | None"] = relationship(
        foreign_keys=[best_candidate_id]
    )
    runner_up: Mapped["LoadProfile | None"] = relationship(
        foreign_keys=[runner_up_id]
    )

    __table_args__ = (
        CheckConstraint("channel IN (1, 2)", name="channel_valid"),
        CheckConstraint(
            "similarity_score >= 0.0 AND similarity_score <= 100.0",
            name="similarity_score_range",
        ),
        CheckConstraint(
            "state IN ('recognized', 'ambiguous', 'unknown', 'insufficient_data')",
            name="state_valid",
        ),
        CheckConstraint(
            "user_feedback IN ('pending', 'confirmed', 'corrected')",
            name="user_response_valid",
        ),
        Index("ix_recognition_events_channel_recognized_at", "channel", "recognized_at"),
    )


class ModeSuggestion(Base):
    """Optimization mode suggestion generated by the AI rule engine."""

    __tablename__ = "mode_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    learning_session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learning_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode_name: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    triggering_values: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped["LearningSession"] = relationship(back_populates="suggestions")

    __table_args__ = (
        Index("ix_mode_suggestions_learning_session_id", "learning_session_id"),
    )


class LoadModeSelection(Base):
    """User-confirmed operating mode enabled for a given load profile."""

    __tablename__ = "load_mode_selections"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("load_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode_name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    selected_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    profile: Mapped["LoadProfile"] = relationship(back_populates="mode_selections")

    __table_args__ = (
        UniqueConstraint(
            "profile_id", "mode_name", name="uq_load_mode_selections_profile_id_mode_name"
        ),
        CheckConstraint(
            "source IN ('ai_suggestion', 'manual', 'saved_profile')",
            name="source_valid",
        ),
        Index("ix_load_mode_selections_profile_id", "profile_id"),
    )
