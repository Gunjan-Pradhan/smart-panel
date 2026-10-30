"""Optimization Mode Suggestions and Rule Engine.

Evaluates load fingerprints against deterministic declarative rules defined
in backend/app/rules/mode_rules.yaml.

AI suggests; human operator explicitly approves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.load_profile import (
    LearningSession,
    LoadModeSelection,
    LoadProfile,
    ModeSuggestion,
    ProfileFingerprint,
)

RULES_FILE_PATH = Path(__file__).resolve().parents[1] / "rules" / "mode_rules.yaml"


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    target_mode: str
    priority: int
    conditions: dict[str, float]
    reason_template: str
    proposed_settings: dict[str, Any]


def load_rules(file_path: Path = RULES_FILE_PATH) -> list[RuleDefinition]:
    """Loads and parses rules from YAML configuration."""
    if not file_path.is_file():
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_rules = data.get("rules", [])
    parsed_rules: list[RuleDefinition] = []
    for r in raw_rules:
        parsed_rules.append(
            RuleDefinition(
                id=r["id"],
                name=r["name"],
                target_mode=r["target_mode"],
                priority=r.get("priority", 100),
                conditions=r.get("conditions", {}),
                reason_template=r["reason_template"],
                proposed_settings=r.get("proposed_settings", {}),
            )
        )
    # Sort rules by priority (ascending: lower number = higher priority)
    parsed_rules.sort(key=lambda r: r.priority)
    return parsed_rules


def evaluate_fingerprint_against_rule(
    fp: ProfileFingerprint,
    rule: RuleDefinition,
) -> tuple[bool, dict[str, Any]]:
    """Evaluates whether a fingerprint satisfies all conditions of a rule."""
    conds = rule.conditions

    # Extract metrics from fingerprint
    p = fp.active_power_mean
    pf = fp.power_factor_mean
    i = fp.current_mean
    q = fp.reactive_power_q
    qs = fp.reactive_ratio_q_s
    cv = fp.cv_power

    # Condition checks
    if "active_power_min" in conds and p < conds["active_power_min"]:
        return False, {}
    if "active_power_max" in conds and p > conds["active_power_max"]:
        return False, {}
    if "power_factor_min" in conds and pf < conds["power_factor_min"]:
        return False, {}
    if "power_factor_max" in conds and pf > conds["power_factor_max"]:
        return False, {}
    if "reactive_ratio_min" in conds and qs < conds["reactive_ratio_min"]:
        return False, {}
    if "reactive_ratio_max" in conds and qs > conds["reactive_ratio_max"]:
        return False, {}
    if "current_min" in conds and i < conds["current_min"]:
        return False, {}
    if "cv_power_min" in conds and cv < conds["cv_power_min"]:
        return False, {}

    triggering = {
        "active_power_w": round(p, 2),
        "power_factor": round(pf, 3),
        "current_a": round(i, 3),
        "reactive_power_q": round(q, 2),
        "reactive_ratio_q_s": round(qs, 3),
        "cv_power": round(cv, 3),
    }
    return True, triggering


class ModeSuggester:
    """Evaluates rules and manages suggestions in the database."""

    def __init__(self, db: Session, rules_path: Path = RULES_FILE_PATH) -> None:
        self.db = db
        self.rules = load_rules(rules_path)

    def generate_suggestions(
        self,
        session_id: uuid.UUID,
        fp: ProfileFingerprint,
    ) -> list[ModeSuggestion]:
        """Evaluates rules against the fingerprint and persists ModeSuggestion records."""
        suggestions: list[ModeSuggestion] = []

        for rule in self.rules:
            matches, values = evaluate_fingerprint_against_rule(fp, rule)
            if not matches:
                continue

            reason = rule.reason_template.format(**values)
            suggestion = ModeSuggestion(
                learning_session_id=session_id,
                mode_name=rule.target_mode,
                rule_id=rule.id,
                reason_text=reason,
                triggering_values={
                    **values,
                    "rule_name": rule.name,
                    "proposed_settings": rule.proposed_settings,
                },
            )
            self.db.add(suggestion)
            suggestions.append(suggestion)

        self.db.commit()
        for s in suggestions:
            self.db.refresh(s)
        return suggestions

    def get_suggestions_by_session(
        self,
        session_id: uuid.UUID,
    ) -> list[ModeSuggestion]:
        """Retrieves all suggestions generated for a learning session."""
        stmt = (
            select(ModeSuggestion)
            .where(ModeSuggestion.learning_session_id == session_id)
            .order_by(ModeSuggestion.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_suggestions_for_profile(
        self,
        profile_id: uuid.UUID,
    ) -> list[ModeSuggestion]:
        """Retrieves suggestions associated with any fingerprint belonging to this profile."""
        stmt = (
            select(ModeSuggestion)
            .join(
                ProfileFingerprint,
                ModeSuggestion.learning_session_id == ProfileFingerprint.learning_session_id,
            )
            .where(ProfileFingerprint.profile_id == profile_id)
            .order_by(ModeSuggestion.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def accept_suggestion(
        self,
        suggestion_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LoadModeSelection:
        """Applies an operator's explicit acceptance of a mode suggestion."""
        suggestion = self.db.get(ModeSuggestion, suggestion_id)
        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found")

        # Find profile associated with this suggestion's session
        stmt = select(ProfileFingerprint).where(
            ProfileFingerprint.learning_session_id == suggestion.learning_session_id
        )
        fp = self.db.execute(stmt).scalars().first()
        if not fp:
            raise ValueError("No profile associated with this suggestion")

        profile_id = fp.profile_id

        # Upsert LoadModeSelection
        stmt_sel = select(LoadModeSelection).where(
            LoadModeSelection.profile_id == profile_id,
            LoadModeSelection.mode_name == suggestion.mode_name,
        )
        selection = self.db.execute(stmt_sel).scalars().first()

        if selection:
            selection.enabled = True
            selection.source = "ai_suggestion"
            selection.selected_by = user_id
        else:
            selection = LoadModeSelection(
                profile_id=profile_id,
                mode_name=suggestion.mode_name,
                enabled=True,
                source="ai_suggestion",
                selected_by=user_id,
            )
            self.db.add(selection)

        self.db.commit()
        self.db.refresh(selection)
        return selection

