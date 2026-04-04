"""Prompted predictor init and label-watcher loop."""

import asyncio
import logging

from user_models.prompted import PromptedPredictor

logger = logging.getLogger(__name__)


async def init_predictor(state, config, loop):
    def _init():
        predictor = PromptedPredictor(
            data_manager=state.model.data_manager,
            model=config.prompted_model,
            api_key=config.default_llm_api_key,
            log_dir=config.log_dir,
            retriever_checkpoint=config.retriever_checkpoint,
        )
        predictor.index_context()
        return predictor

    state.model.predictor = await loop.run_in_executor(None, _init)
    logger.info(f"Prompted predictor initialized (model={config.prompted_model})")


async def run_label_watcher(state):
    """Watch for label updates and broadcast status; no training loop."""
    data_manager = state.model.data_manager
    logger.info("Prompted mode: watching for label updates")
    while True:
        try:
            await asyncio.wait_for(data_manager.wait_for_label(), timeout=5.0)
            screen = state.connectors.get("screen")
            await state.broadcast("status", {
                "recording_active": screen is not None and not screen.paused,
                "training_active": False,
                "labels_processed": data_manager.labels_processed,
            })
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            logger.info("Prompted label watcher cancelled")
            break
