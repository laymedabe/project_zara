"""
Project Zara — WebSocket Manager
=================================
Manages WebSocket connections for real-time dashboard updates.
Broadcasts sensor data, risk assessments, and alerts to all connected clients.
"""

import json
import asyncio
from datetime import datetime, timezone
from fastapi import WebSocket
from typing import Optional


class WebSocketManager:
    """Manages WebSocket connections and broadcasts data to connected dashboards."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message_type: str, data: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        payload = json.dumps({
            "type": message_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })

        disconnected = []
        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(payload)
                except Exception:
                    disconnected.append(connection)

        # Clean up broken connections
        for conn in disconnected:
            await self.disconnect(conn)

    async def broadcast_sensor_data(self, reading: dict):
        """Broadcast new sensor reading to all clients."""
        await self.broadcast("sensor_data", reading)

    async def broadcast_risk_update(self, assessment: dict):
        """Broadcast risk assessment update to all clients."""
        await self.broadcast("risk_update", assessment)

    async def broadcast_alert(self, alert: dict):
        """Broadcast a new alert to all clients."""
        await self.broadcast("alert", alert)

    @property
    def client_count(self) -> int:
        return len(self.active_connections)


# Global WebSocket manager instance
ws_manager = WebSocketManager()
