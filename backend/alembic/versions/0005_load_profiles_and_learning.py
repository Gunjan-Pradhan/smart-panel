"""Migration 0005: load profiles, learning sessions, fingerprints, recognition, mode suggestions.

Schema reference: Section 3.7 of build specification.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. load_profiles
    op.create_table(
        "load_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "user_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("channel_last_seen", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("nominal_power_w", sa.Numeric(9, 2), nullable=True),
        sa.Column("nominal_current_a", sa.Numeric(7, 3), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel_last_seen IS NULL OR channel_last_seen IN (1, 2)",
            name="channel_last_seen_valid",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_load_profiles_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_load_profiles"),
    )
    op.create_index(
        "ix_load_profiles_owner_id", "load_profiles", ["owner_id"]
    )

    # 2. learning_sessions
    op.create_table(
        "learning_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.SmallInteger(), nullable=False),
        sa.Column(
            "start_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'learning'"),
        ),
        sa.Column(
            "valid_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "excluded_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "exclusion_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("sampling_interval_s", sa.Float(), nullable=True),
        sa.Column(
            "feature_set_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'1.0.0'"),
        ),
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("channel IN (1, 2)", name="channel_valid"),
        sa.CheckConstraint(
            "status IN ('learning', 'ready', 'unstable', 'insufficient_data', 'cancelled')",
            name="status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_sessions"),
    )
    op.create_index(
        "ix_learning_sessions_channel_status",
        "learning_sessions",
        ["channel", "status"],
    )

    # 3. profile_fingerprints
    op.create_table(
        "profile_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "learning_session_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("voltage_mean", sa.Float(), nullable=False),
        sa.Column("voltage_std", sa.Float(), nullable=False),
        sa.Column("current_mean", sa.Float(), nullable=False),
        sa.Column("current_std", sa.Float(), nullable=False),
        sa.Column("current_min", sa.Float(), nullable=False),
        sa.Column("current_max", sa.Float(), nullable=False),
        sa.Column("active_power_mean", sa.Float(), nullable=False),
        sa.Column("active_power_std", sa.Float(), nullable=False),
        sa.Column("active_power_min", sa.Float(), nullable=False),
        sa.Column("active_power_max", sa.Float(), nullable=False),
        sa.Column("power_factor_mean", sa.Float(), nullable=False),
        sa.Column("power_factor_std", sa.Float(), nullable=False),
        sa.Column("frequency_mean", sa.Float(), nullable=False),
        sa.Column("frequency_std", sa.Float(), nullable=False),
        sa.Column("apparent_power_s", sa.Float(), nullable=False),
        sa.Column("reactive_power_q", sa.Float(), nullable=False),
        sa.Column("reactive_ratio_q_s", sa.Float(), nullable=False),
        sa.Column("cv_power", sa.Float(), nullable=False),
        sa.Column("power_per_volt_sq", sa.Float(), nullable=False),
        sa.Column("startup_ratio", sa.Float(), nullable=True),
        sa.Column(
            "transition_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "feature_set_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'1.0.0'"),
        ),
        sa.Column(
            "approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["load_profiles.id"],
            name="fk_profile_fingerprints_profile_id_load_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_session_id"],
            ["learning_sessions.id"],
            name="fk_profile_fingerprints_learning_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profile_fingerprints"),
    )
    op.create_index(
        "ix_profile_fingerprints_profile_id",
        "profile_fingerprints",
        ["profile_id"],
    )

    # 4. recognition_events
    op.create_table(
        "recognition_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.SmallInteger(), nullable=False),
        sa.Column(
            "recognized_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "best_candidate_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("runner_up_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column(
            "user_feedback",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "corrected_profile_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.CheckConstraint("channel IN (1, 2)", name="channel_valid"),
        sa.CheckConstraint(
            "similarity_score >= 0.0 AND similarity_score <= 100.0",
            name="similarity_score_range",
        ),
        sa.CheckConstraint(
            "state IN ('recognized', 'ambiguous', 'unknown', 'insufficient_data')",
            name="state_valid",
        ),
        sa.CheckConstraint(
            "user_feedback IN ('pending', 'confirmed', 'corrected')",
            name="user_response_valid",
        ),
        sa.ForeignKeyConstraint(
            ["best_candidate_id"],
            ["load_profiles.id"],
            name="fk_recognition_events_best_candidate_id_load_profiles",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["runner_up_id"],
            ["load_profiles.id"],
            name="fk_recognition_events_runner_up_id_load_profiles",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_profile_id"],
            ["load_profiles.id"],
            name="fk_recognition_events_corrected_profile_id_load_profiles",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recognition_events"),
    )
    op.create_index(
        "ix_recognition_events_channel_recognized_at",
        "recognition_events",
        ["channel", "recognized_at"],
    )

    # 5. mode_suggestions
    op.create_table(
        "mode_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "learning_session_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("mode_name", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column(
            "triggering_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["learning_session_id"],
            ["learning_sessions.id"],
            name="fk_mode_suggestions_learning_session_id_learning_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mode_suggestions"),
    )
    op.create_index(
        "ix_mode_suggestions_learning_session_id",
        "mode_suggestions",
        ["learning_session_id"],
    )

    # 6. load_mode_selections
    op.create_table(
        "load_mode_selections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode_name", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("selected_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "selected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('ai_suggestion', 'manual', 'saved_profile')",
            name="source_valid",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["load_profiles.id"],
            name="fk_load_mode_selections_profile_id_load_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_by"],
            ["users.id"],
            name="fk_load_mode_selections_selected_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_load_mode_selections"),
        sa.UniqueConstraint(
            "profile_id",
            "mode_name",
            name="uq_load_mode_selections_profile_id_mode_name",
        ),
    )
    op.create_index(
        "ix_load_mode_selections_profile_id",
        "load_mode_selections",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_table("load_mode_selections")
    op.drop_table("mode_suggestions")
    op.drop_table("recognition_events")
    op.drop_table("profile_fingerprints")
    op.drop_table("learning_sessions")
    op.drop_table("load_profiles")
