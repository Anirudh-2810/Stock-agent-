from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_queues: Dict[str, asyncio.Queue] = {}
        self._sender_tasks: Dict[str, asyncio.Task] = {}
        self._message_id = 0
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.client_queues[client_id] = asyncio.Queue(maxsize=1000)
        self._sender_tasks[client_id] = asyncio.create_task(self._sender(client_id))
        logger.info(f"Client connected: {client_id}")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.client_queues:
            del self.client_queues[client_id]
        task = self._sender_tasks.pop(client_id, None)
        if task and not task.done():
            task.cancel()
        logger.info(f"Client disconnected: {client_id}")
    
    async def _sender(self, client_id: str):
        queue = self.client_queues.get(client_id)
        ws = self.active_connections.get(client_id)
        if not queue or not ws:
            return
        
        try:
            while True:
                message = await queue.get()
                try:
                    await ws.send_text(message)
                except Exception as e:
                    logger.error(f"Send error for {client_id}: {e}")
                    break
        except asyncio.CancelledError:
            pass
    
    async def broadcast(self, message: dict):
        text = json.dumps(message)
        for client_id, queue in self.client_queues.items():
            try:
                queue.put_nowait(text)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for {client_id}, dropping message")
    
    async def send_personal(self, client_id: str, message: dict):
        queue = self.client_queues.get(client_id)
        if queue:
            try:
                queue.put_nowait(json.dumps(message))
            except asyncio.QueueFull:
                pass


manager = ConnectionManager()