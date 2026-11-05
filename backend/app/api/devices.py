"""Device and channel endpoints with ownership enforcement and command dispatch.

Schema reference: docs/mqtt_contract.md §8-9 and docs/database_schema.md §4.9.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_device_for_user, owned_device_query
from app.config import Settings, get_settings
from app.db.session import get_db
from app.models import Channel, Command, Device, User
from app.schemas.command import CommandAckIn, CommandCreate, CommandOut
from app.schemas.device import ChannelOut, DeviceOut
from app.services.command_service import handle_command_ack, issue_command

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


@router.post(
    "/{device_id}/commands",
    response_model=CommandOut,
    status_code=status.HTTP_201_CREATED,
)
def create_command(
    device_id: str,
    payload: CommandCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Dispatch an authenticated relay command to the device."""
    device = get_device_for_user(db, user, device_id)

    # Permission check: viewers cannot command
    if user.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot issue commands",
        )

    # Ensure requested channel exists on device
    channel = db.scalar(
        select(Channel).where(
            Channel.device_pk == device.id,
            Channel.ch == payload.ch,
        )
    )
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {payload.ch} not found on this device",
        )

    cmd = issue_command(db, device, user, payload, settings)
    return CommandOut(
        cmd_id=cmd.cmd_id,
        device_id=device.device_id,
        ch=cmd.ch,
        action=cmd.action,
        source=cmd.source,
        priority=cmd.priority,
        duration_seconds=cmd.duration_seconds,
        status=cmd.status,
        reason=cmd.reason,
        issued_at=cmd.issued_at,
        expires_at=cmd.expires_at,
        acked_at=cmd.acked_at,
        executed_at=cmd.executed_at,
        relay_after=cmd.relay_after,
        state_after=cmd.state_after,
        created_at=cmd.created_at,
    )


@router.get("/{device_id}/commands", response_model=list[CommandOut])
def list_commands(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CommandOut]:
    """Retrieve recent commands for this device."""
    device = get_device_for_user(db, user, device_id)
    statement = (
        select(Command)
        .where(Command.device_pk == device.id)
        .order_by(Command.issued_at.desc())
        .limit(limit)
    )
    cmds = list(db.scalars(statement).all())
    return [
        CommandOut(
            cmd_id=c.cmd_id,
            device_id=device.device_id,
            ch=c.ch,
            action=c.action,
            source=c.source,
            priority=c.priority,
            duration_seconds=c.duration_seconds,
            status=c.status,
            reason=c.reason,
            issued_at=c.issued_at,
            expires_at=c.expires_at,
            acked_at=c.acked_at,
            executed_at=c.executed_at,
            relay_after=c.relay_after,
            state_after=c.state_after,
            created_at=c.created_at,
        )
        for c in cmds
    ]


@router.post("/{device_id}/commands/ack", response_model=CommandOut)
def receive_command_ack(
    device_id: str,
    ack: CommandAckIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Receive and record command execution acknowledgement."""
    device = get_device_for_user(db, user, device_id)
    cmd = handle_command_ack(db, ack)
    if cmd is None or cmd.device_pk != device.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Command not found for this device",
        )
    return CommandOut(
        cmd_id=cmd.cmd_id,
        device_id=device.device_id,
        ch=cmd.ch,
        action=cmd.action,
        source=cmd.source,
        priority=cmd.priority,
        duration_seconds=cmd.duration_seconds,
        status=cmd.status,
        reason=cmd.reason,
        issued_at=cmd.issued_at,
        expires_at=cmd.expires_at,
        acked_at=cmd.acked_at,
        executed_at=cmd.executed_at,
        relay_after=cmd.relay_after,
        state_after=cmd.state_after,
        created_at=cmd.created_at,
    )
