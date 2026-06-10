"""WebSocket менеджер для real-time чата.

Хранит активные подключения и позволяет отправлять сообщения конкретным пользователям.
"""

from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
import json
from services.auth import unsign_cookie
from config import COOKIE_NAME


class ConnectionManager:
    """Управляет WebSocket подключениями пользователей."""

    def __init__(self):
        # user_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_to_user(self, user_id: int, message: dict):
        """Отправить сообщение конкретному пользователю."""
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(json.dumps(message))

    async def broadcast(self, message: dict):
        """Отправить сообщение всем подключённым пользователям."""
        for connection in self.active_connections.values():
            await connection.send_text(json.dumps(message))


# Глобальный экземпляр менеджера
manager = ConnectionManager()


async def get_user_id_from_cookie(websocket: WebSocket) -> int | None:
    """Извлекает user_id из WebSocket cookie или query params."""
    # Пробуем cookie
    cookies = websocket.cookies
    raw = cookies.get(COOKIE_NAME)
    if raw:
        return unsign_cookie(raw)
    
    # Fallback: пробуем query params
    token = websocket.query_params.get("token")
    if token:
        return unsign_cookie(token)
    
    return None
