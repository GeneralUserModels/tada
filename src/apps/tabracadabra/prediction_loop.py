"""Background prediction loop for tabracadabra — keeps the prediction cache fresh."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_prediction_loop(state) -> None:
    """Periodically run handle_prediction_request while inference is active."""
    from user_models.inference import handle_prediction_request

    logger.info("Prediction loop started (interval=%ss)", state.config.predict_every_n_seconds)
    while True:
        await asyncio.sleep(state.config.predict_every_n_seconds)
        try:
            await handle_prediction_request(state)
        except Exception as e:
            logger.warning("Prediction loop error: %s", e)
