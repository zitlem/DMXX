"""WebSocket connection manager for real-time updates."""
import asyncio
import logging
import uuid
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.client_ids: Dict[WebSocket, str] = {}  # Track client IDs for source tracking

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        self.active_connections.add(websocket)
        client_id = str(uuid.uuid4())[:8]  # Short unique ID for this client
        self.client_ids[websocket] = client_id
        logger.info(f"WebSocket connected (client {client_id}). Total connections: {len(self.active_connections)}")
        return client_id

    def disconnect(self, websocket: WebSocket):
        client_id = self.client_ids.pop(websocket, "unknown")
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected (client {client_id}). Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        dead_connections = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections.discard(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception:
            self.active_connections.discard(websocket)

    async def broadcast_scenes_changed(self):
        """Notify all clients that scene list has changed."""
        await self.broadcast({"type": "scenes_changed"})

    async def broadcast_patches_changed(self):
        """Notify all clients that patch configuration has changed."""
        await self.broadcast({"type": "patches_changed"})

    async def broadcast_group_value_changed(self, group_id: int, value: int, source: str = None):
        """Notify all clients that a group master value has changed."""
        data = {
            "group_id": group_id,
            "value": value
        }
        if source:
            data["source"] = source
        await self.broadcast({
            "type": "group_value_changed",
            "data": data
        })

    async def broadcast_groups_changed(self):
        """Notify all clients that group list has changed (create/update/delete)."""
        await self.broadcast({"type": "groups_changed"})

    async def broadcast_grids_changed(self):
        """Notify all clients that group grid configuration has changed."""
        await self.broadcast({"type": "grids_changed"})


# Global instance
manager = ConnectionManager()
