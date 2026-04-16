"""Background prediction loop for tabracadabra — keeps the prediction cache fresh."""

import asyncio
import logging

from user_models.inference import handle_prediction_request

logger = logging.getLogger(__name__)

_DEBOUNCE_S = 1.0

async def _debounce(data_manager) -> None:
    """Drain rapid label bursts, waiting until quiet for _DEBOUNCE_S."""
    while True:
        try:
            await asyncio.wait_for(data_manager.wait_for_label(), timeout=_DEBOUNCE_S)
        except asyncio.TimeoutError:
            break

def _is_recording(state) -> bool:
    screen = state.connectors.get("screen")
    return screen is not None and not screen.paused


async def run_prediction_loop(state) -> None:
    """Run handle_prediction_request when new labels arrive while recording is active."""
    data_manager = state.model.data_manager
    logger.info("Prediction loop started (interval=%ss)", state.config.predict_every_n_seconds)
    while True:
        try:
            await asyncio.wait_for(
                data_manager.wait_for_label(),
                timeout=state.config.predict_every_n_seconds,
            )
            await _debounce(data_manager)
        except asyncio.TimeoutError:
            continue

        if not _is_recording(state):
            logger.debug("Skipping prediction — recording is not active")
            continue

        try:
            await handle_prediction_request(state, source="auto")
        except Exception as e:
            logger.warning("Prediction loop error: %s", e)
