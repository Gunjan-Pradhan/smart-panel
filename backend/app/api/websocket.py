"""FastAPI WebSocket live telemetry endpoint.

Authoritative live data path for the dashboard (per Workstream 5 requirement 8).
Replaces Node-RED WebSocket with secure, unified FastAPI streaming.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-websocket"])


class ConnectionManager:
    """Manages active live streaming WebSocket connections grouped by device_id."""

    def __init__(self) -> None:
        self._active: Dict[str, Set[WebSocket]] = {}

    async def connect(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if device_id not in self._active:
            self._active[device_id] = set()
        self._active[device_id].add(websocket)
        logger.info("WebSocket connected for device %s (total: %d)", device_id, len(self._active[device_id]))

    def disconnect(self, device_id: str, websocket: WebSocket) -> None:
        if device_id in self._active and websocket in self._active[device_id]:
            self._active[device_id].remove(websocket)
            if not self._active[device_id]:
                del self._active[device_id]
        logger.info("WebSocket disconnected for device %s", device_id)

    async def broadcast(self, device_id: str, data: dict[str, Any]) -> None:
        """Broadcast live telemetry or event to all connected clients for a device."""
        if device_id not in self._active:
            return

        dead_connections: list[WebSocket] = []
        for connection in self._active[device_id]:
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(device_id, dead)


manager = ConnectionManager()


@router.websocket("/ws/live/{device_id}")
async def live_telemetry_ws(websocket: WebSocket, device_id: str) -> None:
    """Stream live telemetry and calculated electrical parameters (S, Q) to the dashboard."""
    await manager.connect(device_id, websocket)
    try:
        while True:
            # Keep connection open; receive ping or client heartbeat
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(device_id, websocket)
    except Exception as exc:
        logger.warning("WebSocket error for device %s: %s", device_id, exc)
        manager.disconnect(device_id, websocket)

