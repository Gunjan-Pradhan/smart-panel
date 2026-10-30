"""Import every model here so Alembic and Base.metadata see the full schema."""

from app.models.audit_log import AuditLog
from app.models.channel import Channel
from app.models.command import Command
from app.models.device import Device
from app.models.event import Event
from app.models.load import Load
from app.models.load_profile import (
    LearningSession,
    LoadModeSelection,
    LoadProfile,
    ModeSuggestion,
    ProfileFingerprint,
    RecognitionEvent,
)
from app.models.refresh_token import RefreshToken
from app.models.schedule import Schedule
from app.models.telemetry import Telemetry
from app.models.user import User

__all__ = [
    "AuditLog",
    "Channel",
    "Command",
    "Device",
    "Event",
    "LearningSession",
    "Load",
    "LoadModeSelection",
    "LoadProfile",
    "ModeSuggestion",
    "ProfileFingerprint",
    "RecognitionEvent",
    "RefreshToken",
    "Schedule",
    "Telemetry",
    "User",
]
