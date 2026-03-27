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

    # Connector instances (populated by connectors service on startup)
    connectors: dict = field(default_factory=dict)
    connector_auth: dict = field(default_factory=dict)  # name → requires_auth value

    # WebSocket connections
    ws_connections: set = field(default_factory=set)

    async def broadcast(self, event: str, data: dict):
        """Push an event to all connected WebSocket clients."""
        import json
        message = json.dumps({"event": event, **data})
        dead = []
        for ws in self.ws_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_connections.discard(ws)
