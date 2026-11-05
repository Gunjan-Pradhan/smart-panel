"""Device and channel endpoints with ownership enforcement, sharing, and command dispatch.

Schema reference: docs/mqtt_contract.md §8-9, docs/database_schema.md §4.9, and Workstream 6.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_device_for_user,
    get_user_device_role,
    owned_device_query,
)
from app.config import Settings, get_settings
from app.db.session import get_db
from app.models import Channel, Command, Device, DeviceMember, User
from app.schemas.command import CommandAckIn, CommandCreate, CommandOut
from app.schemas.device import ChannelOut, DeviceOut, MemberCreate, MemberOut
from app.services.auth import record_audit
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
    device_role = get_user_device_role(db, user, device)

    # Permission check: viewers cannot command
    if device_role == "viewer" or user.role == "viewer":
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
    ch: int | None = Query(default=None, ge=1, le=2),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    """List historical commands for this device."""
    device = get_device_for_user(db, user, device_id)
    statement = (
        select(Command)
        .where(Command.device_pk == device.id)
        .order_by(Command.created_at.desc())
        .limit(limit)
    )
    if ch is not None:
        statement = statement.where(Command.ch == ch)

    commands = db.scalars(statement).all()
    return [
        CommandOut(
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
        for cmd in commands
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


# --------------------------------------------------------------------------
# Multi-User Device Sharing & Membership Endpoints (Workstream 6)
# --------------------------------------------------------------------------


@router.get("/{device_id}/members", response_model=list[MemberOut])
def list_device_members(
    device_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemberOut]:
    """Lists all users shared on this device."""
    device = get_device_for_user(db, user, device_id)
    members = db.scalars(
        select(DeviceMember)
        .where(DeviceMember.device_id == device.id)
        .order_by(DeviceMember.created_at)
    ).all()
    return [
        MemberOut(
            id=m.id,
            device_id=m.device_id,
            user_id=m.user_id,
            email=m.user.email,
            role=m.role,
            created_at=m.created_at,
        )
        for m in members
    ]


@router.post(
    "/{device_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_device_member(
    device_id: str,
    payload: MemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberOut:
    """Shares device with another user (admin or viewer role). Only owner/admin can share."""
    device = get_device_for_user(db, user, device_id)
    device_role = get_user_device_role(db, user, device)
    if device_role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the device owner or administrator can share this device",
        )

    target_user = db.scalar(
        select(User).where(func.lower(User.email) == payload.email.strip().lower())
    )
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if target_user.id == device.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already the owner of this device",
        )

    existing = db.scalar(
        select(DeviceMember).where(
            DeviceMember.device_id == device.id,
            DeviceMember.user_id == target_user.id,
        )
    )
    if existing:
        existing.role = payload.role
        member = existing
    else:
        member = DeviceMember(
            device_id=device.id,
            user_id=target_user.id,
            role=payload.role,
        )
        db.add(member)

    record_audit(
        db,
        action="DEVICE_SHARED",
        entity_type="device",
        entity_id=device.device_id,
        user_id=user.id,
        detail={
            "shared_with": target_user.email,
            "role": payload.role,
        },
    )
    db.commit()
    db.refresh(member)
    return MemberOut(
        id=member.id,
        device_id=member.device_id,
        user_id=member.user_id,
        email=target_user.email,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete(
    "/{device_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_device_member(
    device_id: str,
    member_user_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Revokes device access for a user. Owner/admin or self-removal allowed."""
    device = get_device_for_user(db, user, device_id)
    device_role = get_user_device_role(db, user, device)

    if device_role not in ("owner", "admin") and user.id != member_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the device owner or administrator can remove members",
        )

    member = db.scalar(
        select(DeviceMember).where(
            DeviceMember.device_id == device.id,
            DeviceMember.user_id == member_user_id,
        )
    )
    if member is not None:
        db.delete(member)
        record_audit(
            db,
            action="DEVICE_UNSHARED",
            entity_type="device",
            entity_id=device.device_id,
            user_id=user.id,
            detail={"removed_user_id": str(member_user_id)},
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{device_id}/claim",
    response_model=DeviceOut,
)
def claim_device(
    device_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Claims an unowned panel or confirms existing ownership."""
    device = db.scalar(
        select(Device).where(Device.device_id == device_id)
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    if device.owner_id == user.id:
        return device

    # Strict isolation: if already owned by another user, return 409 or 404
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Device is already claimed by another owner",
    )
