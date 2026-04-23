"""In-process pub/sub for kitchen WebSocket clients (single-worker friendly)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class KitchenHub:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._clients:
                        self._clients.remove(ws)


kitchen_hub = KitchenHub()


async def notify_kitchen_order_created(order_summary: dict[str, Any]) -> None:
    await kitchen_hub.broadcast_json({"event": "order_created", "order": order_summary})
