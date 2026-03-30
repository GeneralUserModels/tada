"""Training service — dispatches to the appropriate model-type training module."""

import asyncio
import logging
from typing import Any

from user_models.powernap.training import (
    init_trainer as powernap_init_trainer,
    init_predictor as powernap_init_predictor,
    run_training_loop,
)
from user_models.prompted.training import (
    init_predictor as prompted_init_predictor,
    run_label_watcher,
)

logger = logging.getLogger(__name__)


async def init_model(state: Any) -> None:
    """Initialize trainer + predictor for the configured model type.

    Called once at startup after DataManager is running. Does not start any loops.
    """
    config = state.config
    loop = asyncio.get_running_loop()

    if config.model_type == "powernap":
        try:
            await powernap_init_trainer(state, config, loop)
        except Exception:
            logger.exception("Powernap trainer init failed; predictor unavailable until config is fixed and server restarted")
            return  # predictor depends on trainer
        await powernap_init_predictor(state, config, loop)
    else:
        await prompted_init_predictor(state, config, loop)


async def run_training_service(state: Any) -> None:
    """Long-running background loop. Expects init_model already called.

    For powernap: runs training loop (pauses on training_resumed event).
    For prompted: watches for label updates.
    """
    config = state.config

    if config.model_type == "powernap":
        if state.model.trainer is None:
            logger.warning("Trainer not initialized (check API key/model config); training unavailable")
            return
        await run_training_loop(state)
    else:
        await run_label_watcher(state)
