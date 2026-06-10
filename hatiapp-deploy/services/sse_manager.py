"""SSE (Server-Sent Events) менеджер для real-time уведомлений.

Используется для отправки уведомлений о новых сообщениях,
записях на смены и других событиях.
"""

import asyncio
import json
from typing import Dict, List
from fastapi import Request
from starlette.responses import StreamingResponse


class SSEManager:
    """Управляет SSE соединениями пользователей."""

    def __init__(self):
        # user_id -> список очередей
        self.connections: Dict[int, List[asyncio.Queue]] = {}

    async def connect(self, user_id: int) -> asyncio.Queue:
        """Создаёт новое SSE соединение для пользователя."""
        queue = asyncio.Queue()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(queue)
        return queue

    def disconnect(self, user_id: int, queue: asyncio.Queue):
        """Закрывает SSE соединение."""
        if user_id in self.connections:
            if queue in self.connections[user_id]:
                self.connections[user_id].remove(queue)
            if not self.connections[user_id]:
                del self.connections[user_id]

    async def send_to_user(self, user_id: int, data: dict):
        """Отправляет уведомление конкретному пользователю."""
        if user_id in self.connections:
            message = json.dumps(data)
            for queue in self.connections[user_id]:
                await queue.put(message)

    async def broadcast(self, data: dict):
        """Отправляет уведомление всем подключённым пользователям."""
        message = json.dumps(data)
        for queues in self.connections.values():
            for queue in queues:
                await queue.put(message)


# Глобальный экземпляр
sse_manager = SSEManager()


async def sse_stream(request: Request, user_id: int):
    """Генератор SSE потока для конкретного пользователя."""
    queue = await sse_manager.connect(user_id)

    async def event_generator():
        try:
            while True:
                # Ждём сообщение из очереди с таймаутом
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Отправляем heartbeat для поддержания соединения
                    yield ":heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            sse_manager.disconnect(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
