"""Server-Sent Events (SSE) manager for real-time video status updates."""

import logging
import asyncio
from typing import Dict, Set, Callable, Any
from asyncio import Queue

logger = logging.getLogger(__name__)


class SSEClient:
    """Represents a connected SSE client."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.queue: Queue = Queue()
        self.connected = True

    async def send(self, data: dict) -> None:
        """Send data to the client."""
        if self.connected:
            try:
                await self.queue.put(data)
            except Exception as e:
                logger.error(f"Error sending to SSE client {self.client_id}: {e}")

    async def disconnect(self) -> None:
        """Mark client as disconnected."""
        self.connected = False


class SSEManager:
    """Manages SSE connections for real-time updates."""

    def __init__(self):
        # Structure: {video_id: {client_id: SSEClient}}
        self.clients: Dict[str, Dict[str, SSEClient]] = {}

    def add_client(self, video_id: str, client_id: str) -> SSEClient:
        """Register a new SSE client for a video."""
        if video_id not in self.clients:
            self.clients[video_id] = {}

        client = SSEClient(client_id)
        self.clients[video_id][client_id] = client
        logger.info(f"SSE client {client_id} connected to video {video_id}")
        return client

    def remove_client(self, video_id: str, client_id: str) -> None:
        """Unregister an SSE client."""
        if video_id in self.clients and client_id in self.clients[video_id]:
            del self.clients[video_id][client_id]
            logger.info(f"SSE client {client_id} disconnected from video {video_id}")

            # Clean up empty video entries
            if not self.clients[video_id]:
                del self.clients[video_id]

    async def broadcast(self, video_id: str, data: dict) -> None:
        """Broadcast a message to all connected clients for a video."""
        if video_id not in self.clients:
            logger.debug(f"No connected clients for video {video_id}")
            return

        client_ids = list(self.clients[video_id].keys())
        logger.info(f"Broadcasting to {len(client_ids)} clients for video {video_id}")

        # Send to all clients concurrently
        tasks = [
            self.clients[video_id][client_id].send(data)
            for client_id in client_ids
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_client_count(self, video_id: str) -> int:
        """Get number of connected clients for a video."""
        return len(self.clients.get(video_id, {}))


# Global SSE manager instance
sse_manager = SSEManager()


def get_sse_manager() -> SSEManager:
    """Get the global SSE manager."""
    return sse_manager
