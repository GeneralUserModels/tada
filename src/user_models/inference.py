"""Inference service — on-demand prediction triggered by WebSocket request."""

import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from user_models.powernap.longnap.trainer_utils import build_actions_block

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


async def handle_prediction_request(state: Any):
    """Handle an on-demand prediction request from the client."""
    

    model = state.model

    if model.predictor is None:
        await state.broadcast("prediction", {"error": "predictor not initialized (start training first)"})
        return

    config = state.config
    predictor = model.predictor
    trainer = model.trainer
    data_manager = model.data_manager
    past_len = config.past_len
    future_len = config.future_len

    prediction_events = [e for e in data_manager.buffer if e.get("prediction_event")]

    if len(prediction_events) < past_len:
        await state.broadcast("prediction", {
            "error": f"not enough data ({len(prediction_events)}/{past_len})"
        })
        return

    if trainer is not None:
        path = getattr(trainer, "latest_sampler_path", None)
        if path:
            predictor.model_path = path
        predictor.sampling_client = trainer.sampling_client

    cutoff_ts = time.time()
    snapshot = [e for e in prediction_events if e["timestamp"] < cutoff_ts][-past_len:]

    if len(snapshot) < past_len:
        await state.broadcast("prediction", {
            "error": f"not enough pre-cutoff items ({len(snapshot)}/{past_len})"
        })
        return

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            lambda: predictor.predict_from_snapshot(
                snapshot, future_len,
                num_imgs_per_sample=config.num_imgs_per_sample,
            ),
        )
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        await state.broadcast("prediction", {"error": str(e)})
        return

    state.model.latest_prediction = result

    await state.broadcast("prediction", {
        "actions": result["actions"],
        "think": result.get("think", ""),
        "revise": result.get("revise", ""),
        "timestamp": result["timestamp"],
    })

    actions_parsed = bool(re.search(r"<action>", result["actions"]))
    if actions_parsed and predictor.should_score_prediction:
        asyncio.create_task(_score_prediction(state, result, cutoff_ts, future_len))


async def _score_prediction(state: Any, result: dict, cutoff_ts: float, future_len: int):
    """Background task: wait for enough ground truth, then score the prediction."""
    
    data_manager = state.model.data_manager

    for _ in range(120):
        future = [
            e for e in data_manager.buffer
            if e.get("prediction_event") and e["timestamp"] > cutoff_ts
        ]
        if len(future) >= future_len:
            break
        await asyncio.sleep(1.0)
    else:
        logger.warning("Score timeout: not enough future items")
        return

    ground_truth = build_actions_block(future[:future_len])

    config = state.config
    predictor = state.model.predictor

    loop = asyncio.get_running_loop()
    try:
        reward = await loop.run_in_executor(
            _executor,
            lambda: predictor.score_prediction(
                result["actions"], ground_truth, config.reward_llm,
                api_key=config.reward_llm_api_key or config.default_llm_api_key,
            ),
        )
    except Exception as e:
        logger.warning(f"Score prediction failed: {e}")
        return

    score_data = {"reward": reward, "accuracy": 0.0, "formatting": 0.0, "penalty": 0.0}
    state.model.latest_scores = score_data

    await state.broadcast("score", score_data)
    logger.info(f"Prediction scored: {score_data}")
