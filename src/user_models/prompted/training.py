"""Prompted predictor init and label-watcher loop."""

import asyncio
import logging
from pathlib import Path

from user_models.prompted import PromptedPredictor

logger = logging.getLogger(__name__)

_STATE_SUBDIR = ".prompted_predictor_state"


def _state_dir(config) -> Path:
    return Path(config.log_dir) / _STATE_SUBDIR


async def init_predictor(state, config, loop):
    state_dir = _state_dir(config)

    def _init():
        predictor = PromptedPredictor(
            data_manager=state.model.data_manager,
            model=config.prompted_model,
            api_key=config.resolve_api_key("default_llm_api_key"),
            log_dir=config.log_dir,
            # Honor explicit checkpoint when set; otherwise the auto-state path below
            # restores both the retriever and caption bookkeeping.
            retriever_checkpoint=config.retriever_checkpoint,
        )
        if not config.retriever_checkpoint:
            predictor.load_state(state_dir)
        predictor.index_context()
        return predictor

    state.model.predictor = await loop.run_in_executor(None, _init)
    logger.info(f"Prompted predictor initialized (model={config.prompted_model})")


async def run_label_watcher(state):
    """Watch for label updates, broadcast status. Saves predictor state on shutdown only."""
    data_manager = state.model.data_manager
    config = state.config
    logger.info("Prompted mode: watching for label updates")
    try:
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
        logger.info("Prompted label watcher cancelled — saving predictor state")
        predictor = state.model.predictor
        if predictor is not None:
            # Run in executor so we don't block the event loop on a multi-second
            # gzip+json dump. The dev supervisor's SIGTERM→SIGKILL window is sized
            # large enough (see scripts/dev-supervisor.cjs) to let this finish.
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, predictor.save_state, _state_dir(config)
                )
            except Exception:
                logger.warning("Failed to save prompted predictor state", exc_info=True)
        raise
