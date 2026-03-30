"""Training service — dispatches to the appropriate model-type training module."""

import asyncio
import logging
from typing import Any

from user_models.data_manager import DataManager
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


async def run_training_service(state: Any):
    config = state.config
    loop = asyncio.get_running_loop()

    # ── DataManager init (shared by all model types) ───────────────────────────
    if state.model.data_manager is None:
        dm = DataManager(log_dir=config.log_dir)
        await dm.start()
        state.model.data_manager = dm
        logger.info("DataManager started")

    # ── Dispatch ───────────────────────────────────────────────────────────────
    if config.model_type == "powernap":
        await powernap_init_trainer(state, config, loop)
        if state.model.predictor is None:
            await powernap_init_predictor(state, config, loop)
        await run_training_loop(state)

    else:
        if state.model.predictor is None:
            await prompted_init_predictor(state, config, loop)
        await run_label_watcher(state)
