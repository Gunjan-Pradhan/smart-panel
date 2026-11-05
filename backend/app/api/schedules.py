"""REST API for Schedule management (Workstream 7: Local Schedules & Timers).

Endpoints
---------
POST   /schedules              → create a schedule (owner only / admin member)
GET    /schedules              → list all schedules owned by the current user
GET    /schedules/{id}         → get a single schedule
PATCH  /schedules/{id}         → update fields (name, days, times, timezone, enabled)
DELETE /schedules/{id}         → delete a schedule (returns 204)

After every create or update the backend tries to publish a SCHEDULE_SYNC message
to the device over MQTT so the ESP32 can update its internal timer list in real
time.  If MQTT is unavailable the schedule is still saved and the firmware will
receive the full list next time it reconnects (the firmware polls on reconnect).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import timezone as dt_timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_device_for_user, get_user_device_role
from app.db.session import get_db
from app.models import Device, Schedule, User
from app.schemas.schedule import ScheduleCreate, ScheduleOut, ScheduleUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["schedules"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_schedule_or_404(
    db: Session, schedule_id: uuid.UUID, user: User
) -> Schedule:
    """Return the schedule or raise 404 (never 403 — tenant isolation rule)."""
    sched = db.get(Schedule, schedule_id)
    if sched is None or sched.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return sched


def _schedule_to_out(sched: Schedule, device_id: str) -> ScheduleOut:
    """Build a ScheduleOut from a Schedule ORM row + the device's string device_id."""
    return ScheduleOut(
        id=sched.id,
        device_id=device_id,
        ch=sched.ch,
        name=sched.name,
        days_of_week=sched.days_of_week,
        on_time=sched.on_time,
        off_time=sched.off_time,
        timezone=sched.timezone,
        enabled=sched.enabled,
    )


def _publish_schedule_sync(db: Session, device: Device, ch: int) -> None:
    """
    Publish all enabled schedules for a channel to MQTT so the firmware can
    update its internal timer list immediately.

    This is best-effort: if MQTT is unavailable we log a warning and move on.
    The firmware will request a full sync when it reconnects.
    """
    try:
        # Lazy import so the router works even if paho-mqtt is not installed.
        import paho.mqtt.publish as mqtt_publish  # type: ignore

        from app.config import get_settings

        settings = get_settings()

        # Collect all schedules for this device + channel
        schedules = db.scalars(
            select(Schedule).where(
                Schedule.device_pk == device.id,
                Schedule.ch == ch,
            )
        ).all()

        payload = {
            "action": "SCHEDULE_SYNC",
            "ch": ch,
            "schedules": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "days_of_week": s.days_of_week,
                    "on_time": s.on_time.strftime("%H:%M:%S"),
                    "off_time": s.off_time.strftime("%H:%M:%S"),
                    "timezone": s.timezone,
                    "enabled": s.enabled,
                }
                for s in schedules
            ],
        }

        topic = f"panel/{device.device_id}/cmd"
        mqtt_publish.single(
            topic=topic,
            payload=json.dumps(payload),
            qos=1,
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
        )
        logger.info(
            "SCHEDULE_SYNC published to %s (%d schedule(s))", topic, len(schedules)
        )
    except Exception as exc:  # noqa: BLE001
        # MQTT unavailable — schedule is stored; firmware will sync on reconnect.
        logger.warning("SCHEDULE_SYNC publish skipped (MQTT unavailable): %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ScheduleOut)
def create_schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    """Create a new schedule.

    The calling user must be the owner of the device or an *admin* member.
    Viewers cannot create schedules.
    """
    # Resolve the device (applies tenant isolation automatically)
    device = get_device_for_user(db, user, body.device_id)

    # Only owners and admin members may create schedules
    role = get_user_device_role(db, user, device)
    if role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create schedules",
        )

    # Validate that on_time != off_time (belt-and-suspenders; DB also enforces it)
    if body.on_time == body.off_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="on_time and off_time must be different",
        )

    sched = Schedule(
        owner_id=user.id,
        device_pk=device.id,
        ch=body.ch,
        name=body.name,
        days_of_week=body.days_of_week,
        on_time=body.on_time,
        off_time=body.off_time,
        timezone=body.timezone,
        enabled=body.enabled,
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)

    # Best-effort MQTT sync
    _publish_schedule_sync(db, device, body.ch)

    return _schedule_to_out(sched, device.device_id)


@router.get("", response_model=List[ScheduleOut])
def list_schedules(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[ScheduleOut]:
    """List all schedules owned by the current user (across all their devices)."""
    rows = db.execute(
        select(Schedule, Device.device_id)
        .join(Device, Device.id == Schedule.device_pk)
        .where(Schedule.owner_id == user.id)
        .order_by(Schedule.ch, Schedule.on_time)
    ).all()

    return [_schedule_to_out(sched, dev_id) for sched, dev_id in rows]


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(
    schedule_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    """Return a single schedule (404 if it does not belong to the caller)."""
    sched = _get_schedule_or_404(db, schedule_id, user)
    device = db.get(Device, sched.device_pk)
    return _schedule_to_out(sched, device.device_id)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: uuid.UUID,
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    """Update one or more fields of a schedule (PATCH — only provided fields change)."""
    sched = _get_schedule_or_404(db, schedule_id, user)
    device = db.get(Device, sched.device_pk)

    # Apply only the fields that were provided
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sched, field, value)

    # Re-validate on_time != off_time after potential partial update
    if sched.on_time == sched.off_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="on_time and off_time must be different",
        )

    # Bump updated_at manually (server_default only sets it on INSERT)
    from datetime import datetime

    sched.updated_at = datetime.now(dt_timezone.utc)

    db.commit()
    db.refresh(sched)

    # Best-effort MQTT sync
    _publish_schedule_sync(db, device, sched.ch)

    return _schedule_to_out(sched, device.device_id)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a schedule.  Returns 204 No Content on success, 404 if not found."""
    sched = _get_schedule_or_404(db, schedule_id, user)
    ch = sched.ch
    device = db.get(Device, sched.device_pk)

    db.delete(sched)
    db.commit()

    # Sync the now-shorter schedule list to the firmware
    _publish_schedule_sync(db, device, ch)

