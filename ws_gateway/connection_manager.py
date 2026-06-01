"""
WebSocket Connection Manager — manages active connections per user_id.

Supports multiple tabs/devices per user with a configurable max limit (default: 5).
When limit exceeded, the oldest connection is closed to free resources.
"""

import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_USER = 5


class ConnectionManager:
    def __init__(self):
        # { user_id: [list of active WebSocket connections] }
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Accept a WebSocket connection and register it under user_id."""
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        # Enforce max connections per user — close oldest if exceeded
        while len(self.active_connections[user_id]) >= MAX_CONNECTIONS_PER_USER:
            oldest = self.active_connections[user_id].pop(0)
            try:
                await oldest.close(code=4001, reason="Too many connections")
                logger.info(f"Closed oldest connection for user {user_id} (limit: {MAX_CONNECTIONS_PER_USER})")
            except Exception:
                pass  # Already disconnected

        self.active_connections[user_id].append(websocket)
        total = len(self.active_connections[user_id])
        logger.info(f"User {user_id} connected. Active connections: {total}")

    def disconnect(self, user_id: str, websocket: WebSocket):
        """Remove a WebSocket connection from the registry."""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass  # Already removed

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                logger.info(f"User {user_id} fully disconnected (0 connections)")
            else:
                remaining = len(self.active_connections[user_id])
                logger.info(f"User {user_id} disconnected 1 tab. Remaining: {remaining}")

    async def send_personal_message(self, message: dict, user_id: str):
        """Send a JSON message to ALL active connections of a user."""
        if user_id not in self.active_connections:
            return

        dead_connections = []
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        # Cleanup ghost connections
        for dead in dead_connections:
            self.disconnect(user_id, dead)

    async def broadcast(self, message: dict):
        """Send a JSON message to ALL connected users."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

    @property
    def connection_count(self) -> int:
        """Total number of active WebSocket connections across all users."""
        return sum(len(conns) for conns in self.active_connections.values())

    @property
    def user_count(self) -> int:
        """Number of unique users currently connected."""
        return len(self.active_connections)
