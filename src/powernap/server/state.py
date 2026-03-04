"""ServerState: central shared state, queues, component instances, metrics."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from powernap.server.config import ServerConfig


@dataclass
class ServerState:
    config: ServerConfig = field(default_factory=ServerConfig)

    # Runtime flags
    recording_active: bool = False
    training_active: bool = False
    inference_active: bool = False

    # Async queues (fed by HTTP endpoint, consumed by services)
    aggregation_queue: asyncio.Queue | None = None
    label_queue: asyncio.Queue | None = None

    # Inference buffer (list of labeled dicts, shared with inference service)
    inference_buffer: list = field(default_factory=list)

    # Recording persistence
    recordings_dir: Path | None = None

    # Component instances (lazy-initialized)
    labeler: Any = None
    trainer: Any = None
    predictor: Any = None

    # Service tasks
    labeling_task: asyncio.Task | None = None
    training_task: asyncio.Task | None = None

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
