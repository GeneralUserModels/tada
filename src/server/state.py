"""ServerState: central shared state, queues, component instances, metrics."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from server.config import ServerConfig


@dataclass
class ServerState:
    config: ServerConfig = field(default_factory=ServerConfig)

    # Runtime flags
    recording_active: bool = False
    training_active: bool = False
    inference_active: bool = False

    # Resume events (set when active, cleared when paused)
    recording_resumed: asyncio.Event = field(default_factory=asyncio.Event)
    training_resumed: asyncio.Event = field(default_factory=asyncio.Event)

    # Async queues (fed by context_logging, consumed by training)
    aggregation_queue: asyncio.Queue | None = None
    label_queue: asyncio.Queue | None = None

    # Unified context buffer: all connector events, each with a prediction_event flag
    context_buffer: list = field(default_factory=list)

    # Component instances (lazy-initialized)
    trainer: Any = None
    predictor: Any = None

    # Service tasks
    training_task: asyncio.Task | None = None
    context_logging_task: asyncio.Task | None = None

    # Connector instances (populated by context_logging service)
    connectors: dict = field(default_factory=dict)

    # Metrics
    step_count: int = 0
    untrained_batches: int = 0
    labels_processed: int = 0
    latest_scores: dict = field(default_factory=dict)

    # WebSocket connections
    ws_connections: set = field(default_factory=set)

    def __post_init__(self):
        self.aggregation_queue = asyncio.Queue()
        self.label_queue = asyncio.Queue()
