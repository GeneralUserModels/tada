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

    # Moments executor: BoundedSemaphore caps concurrent tada executions at
    # config.moments_executor_concurrency. Created lazily so config.load_persisted()
    # can override the default before the first acquisition.
    _moments_executor_sem: object = None  # asyncio.BoundedSemaphore | None
    # Serializes appends to logs-tada/results/_runs.jsonl across concurrent runs.
    moments_runs_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # In-flight execution tasks (so we can cancel them on shutdown).
    moments_execution_tasks: set = field(default_factory=set)
    # Slugs currently executing or queued on the semaphore — prevents the
    # scheduler from re-dispatching the same slug while a prior task is still
    # waiting to acquire a slot.
    moments_in_flight_slugs: set = field(default_factory=set)

    @property
    def moments_executor_sem(self) -> asyncio.BoundedSemaphore:
        if self._moments_executor_sem is None:
            n = max(1, int(getattr(self.config, "moments_executor_concurrency", 1) or 1))
            self._moments_executor_sem = asyncio.BoundedSemaphore(n)
        return self._moments_executor_sem

    # Seeker
    seeker_scheduler_task: asyncio.Task | None = None
    seeker_session: object | None = None  # ChatSession when active

    # Moment feedback — one ChatSession per slug, supports concurrent sessions
    feedback_sessions: dict[str, object] = field(default_factory=dict)
    
    cost_logger_task: asyncio.Task | None = None

    # Connector instances (populated by connectors service on startup)
    connectors: dict = field(default_factory=dict)
    connector_auth: dict = field(default_factory=dict)  # name → requires_auth value

    # Tabracadabra event tap service (macOS only)
    tabracadabra_service: object | None = None

    # SSE client queues
    sse_queues: set = field(default_factory=set)

    # Active background-agent activities keyed by agent name (empty when idle)
    active_agents: dict[str, dict] = field(default_factory=dict)

    @property
    def current_activity(self) -> dict | None:
        """Legacy accessor — returns the first active agent or None."""
        if not self.active_agents:
            return None
        return next(iter(self.active_agents.values()))

    async def broadcast(self, event: str, data: dict):
        """Push an event to all connected SSE clients."""
        message = {"event": event, **data}
        for q in list(self.sse_queues):
            await q.put(message)

    async def broadcast_activity(
        self,
        agent: str,
        message: str | None = None,
        *,
        slug: str | None = None,
        num_turns: int | None = None,
        max_turns: int | None = None,
        cadence: str | None = None,
    ):
        """Set or clear a single agent's activity. Pass message=None to clear."""
        if message:
            info: dict = {
                "agent": agent,
                "message": message,
                "num_turns": num_turns,
                "max_turns": max_turns,
            }
            if slug is not None:
                info["slug"] = slug
            if cadence is not None:
                info["cadence"] = cadence
            self.active_agents[agent] = info
        else:
            self.active_agents.pop(agent, None)
        await self.broadcast("agent_activity", {
            "agent": agent,
            "message": message,
            "slug": slug,
            "num_turns": num_turns,
            "max_turns": max_turns,
            "cadence": cadence,
        })

    def make_round_callback(
        self, agent: str, message: str, *,
        slug: str | None = None, cadence: str | None = None,
    ) -> Callable[[int, int], None]:
        """Build a thread-safe callback that broadcasts round progress for (agent, message).

        The agent runs in a worker thread (via asyncio.to_thread), but broadcast_activity
        is a coroutine on the event loop — so we capture the loop here and schedule the
        broadcast via run_coroutine_threadsafe from within the worker.
        """
        loop = asyncio.get_running_loop()

        def on_round(num_turns: int, max_turns: int) -> None:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_activity(
                    agent, message, slug=slug, cadence=cadence,
                    num_turns=num_turns, max_turns=max_turns,
                ),
                loop,
            )

        return on_round
