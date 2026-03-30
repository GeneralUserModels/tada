"""ServerState: central shared state for server infrastructure."""

import asyncio
from dataclasses import dataclass, field

from server.config import ServerConfig
from user_models.model_state import ModelState


@dataclass
class ServerState:
    config: ServerConfig = field(default_factory=ServerConfig)
    model: ModelState = field(default_factory=ModelState)

    # Service tasks
    context_logging_task: asyncio.Task | None = None
    google_refresh_task: asyncio.Task | None = None
    outlook_refresh_task: asyncio.Task | None = None
    prediction_loop_task: asyncio.Task | None = None

    # Connector instances (populated by connectors service on startup)
    connectors: dict = field(default_factory=dict)
    connector_auth: dict = field(default_factory=dict)  # name → requires_auth value

    # SSE client queues
    sse_queues: set = field(default_factory=set)

    async def broadcast(self, event: str, data: dict):
        """Push an event to all connected SSE clients."""
        message = {"event": event, **data}
        for q in list(self.sse_queues):
            await q.put(message)
