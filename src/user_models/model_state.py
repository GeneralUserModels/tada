"""ModelState: runtime state for the user model subsystem.

To add a new model type:
  1. Initialize data_manager, trainer (optional), and predictor in server/services/training.py
  2. Add control routes in server/routes/control.py if needed
  3. Read predictor / data_manager from here in your inference handler
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelState:
    # Training coordination — training_active is True while training_resumed is set
    training_resumed: asyncio.Event = field(default_factory=asyncio.Event)
    training_task: asyncio.Task | None = None

    # Inference toggle (independent of training)
    inference_active: bool = False

    # Component instances (lazy-initialized on first training start)
    data_manager: Any = None
    trainer: Any = None
    predictor: Any = None

    # Latest inference scores (written by inference service after scoring)
    latest_scores: dict = field(default_factory=dict)

    @property
    def training_active(self) -> bool:
        return self.training_resumed.is_set()
