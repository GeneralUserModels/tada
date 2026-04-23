"""ServerState: central shared state for server infrastructure."""

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from server.config import ServerConfig
from user_models.model_state import ModelState


@dataclass
class ServerState:
    config: ServerConfig = field(default_factory=ServerConfig)
    model: ModelState = field(default_factory=ModelState)

    # Whether heavy services have been started
    services_started: bool = False
    _services_starting: bool = False
    connectors_ready: asyncio.Event = field(default_factory=asyncio.Event)

    # Service tasks
    context_logging_task: asyncio.Task | None = None
    moments_scheduler_task: asyncio.Task | None = None
    moments_discovery_task: asyncio.Task | None = None
    memory_task: asyncio.Task | None = None

    # Moments executor lock (one at a time)
    moments_executor_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Seeker
    seeker_scheduler_task: asyncio.Task | None = None
    seeker_session: object | None = None  # ChatSession when active

    # Moment feedback
    feedback_session: object | None = None  # ChatSession when active
    feedback_slug: str | None = None        # which moment is being given feedback
    
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

    # Current background-agent activity (None when idle)
    current_activity: dict | None = None

    async def broadcast(self, event: str, data: dict):
        """Push an event to all connected SSE clients."""
        message = {"event": event, **data}
        for q in list(self.sse_queues):
            await q.put(message)

    async def broadcast_activity(
        self,
        agent: str | None,
        message: str | None = None,
        *,
        num_turns: int | None = None,
        max_turns: int | None = None,
    ):
        """Set and broadcast the current agent activity. Pass agent=None to clear."""
        if agent:
            self.current_activity = {
                "agent": agent,
                "message": message,
                "num_turns": num_turns,
                "max_turns": max_turns,
            }
        else:
            self.current_activity = None
        await self.broadcast("agent_activity", {
            "agent": agent,
            "message": message,
            "num_turns": num_turns,
            "max_turns": max_turns,
        })

    def make_round_callback(self, agent: str, message: str) -> Callable[[int, int], None]:
        """Build a thread-safe callback that broadcasts round progress for (agent, message).

        The agent runs in a worker thread (via asyncio.to_thread), but broadcast_activity
        is a coroutine on the event loop — so we capture the loop here and schedule the
        broadcast via run_coroutine_threadsafe from within the worker.
        """
        loop = asyncio.get_running_loop()

        def on_round(num_turns: int, max_turns: int) -> None:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_activity(agent, message, num_turns=num_turns, max_turns=max_turns),
                loop,
            )

        return on_round
