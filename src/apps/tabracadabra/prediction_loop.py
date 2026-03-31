"""Background prediction loop for tabracadabra — keeps the prediction cache fresh."""

import asyncio
import logging

from litellm import completion as litellm_completion

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

async def _warm_tabracadabra_cache(state) -> None:
    """Send a cheap request with the predictor's conversation to prime the provider cache."""
    prediction = state.model.latest_prediction
    if not prediction or "messages" not in prediction:
        return
    messages = prediction["messages"] + [{"role": "user", "content": "ok"}]
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: litellm_completion(
        model=state.config.tabracadabra_model or prediction["model"],
        messages=messages,
        max_tokens=1,
        api_key=state.config.tabracadabra_api_key or state.config.default_llm_api_key or None,
    ))
    logger.info("Tabracadabra cache warmup completed")


async def run_prediction_loop(state) -> None:
    """Run handle_prediction_request when new labels arrive, or on a fallback interval."""
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
            pass
        try:
            await handle_prediction_request(state)
        except Exception as e:
            logger.warning("Prediction loop error: %s", e)
        try:
            await _warm_tabracadabra_cache(state)
        except Exception as e:
            logger.warning("Cache warmup error: %s", e)
