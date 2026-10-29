"""Read-only device endpoints with ownership enforcement.

Command and telemetry endpoints arrive in later phases. These endpoints exist
now so that authorization can be proven before any control path is added.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_device_for_user, owned_device_query
from app.db.session import get_db
from app.models import Channel, Device, User
from app.schemas.device import ChannelOut, DeviceOut

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    statement = owned_device_query(user).order_by(Device.device_id)
    return list(db.scalars(statement).all())


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_device_for_user(db, user, device_id)


@router.get("/{device_id}/channels", response_model=list[ChannelOut])
def list_channels(
    device_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    device = get_device_for_user(db, user, device_id)
    statement = (
        select(Channel)
        .where(Channel.device_pk == device.id)
        .order_by(Channel.ch)
    )
    return list(db.scalars(statement).all())
