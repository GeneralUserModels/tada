"""ServerState: central shared state for server infrastructure."""

import asyncio
from dataclasses import dataclass, field

from server.config import ServerConfig
from user_models.model_state import ModelState


@dataclass
class ServerState:
    config: ServerConfig = field(default_factory=ServerConfig)
    model: ModelState = field(default_factory=ModelState)

    # Whether heavy services have been started
    services_started: bool = False

    # Service tasks
    context_logging_task: asyncio.Task | None = None
    token_refresh_task: asyncio.Task | None = None
    moments_scheduler_task: asyncio.Task | None = None
    moments_discovery_task: asyncio.Task | None = None
    memory_task: asyncio.Task | None = None

    # Moments executor lock (one at a time)
    moments_executor_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Seeker
    seeker_scheduler_task: asyncio.Task | None = None
    seeker_messages: list[dict] = field(default_factory=list)
    seeker_conversation_active: bool = False
    
    # For Tabracadabra
    prediction_loop_task: asyncio.Task | None = None
    cost_logger_task: asyncio.Task | None = None

    # Connector instances (populated by connectors service on startup)
    connectors: dict = field(default_factory=dict)
    connector_auth: dict = field(default_factory=dict)  # name → requires_auth value

    # Tabracadabra event tap service (macOS only)
    tabracadabra_service: object | None = None

    # SSE client queues
    sse_queues: set = field(default_factory=set)

    async def broadcast(self, event: str, data: dict):
        """Push an event to all connected SSE clients."""
        message = {"event": event, **data}
        for q in list(self.sse_queues):
            await q.put(message)
