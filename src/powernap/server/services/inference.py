"""Inference service — on-demand prediction triggered by WebSocket request."""

import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


async def handle_prediction_request(state: Any):
    """Handle an on-demand prediction request from the client.

    Triggered by a WebSocket 'request_prediction' event. Runs the prediction
    in a thread pool, then broadcasts the result + schedules background eval.
    """
    from powernap.server.ws.handler import broadcast

    if not state.inference_active:
        await broadcast(state, "prediction", {"error": "inference not active"})
        return

    if state.predictor is None or state.trainer is None:
        await broadcast(state, "prediction", {"error": "predictor not initialized (start training first)"})
        return

    config = state.config
    predictor = state.predictor
    trainer = state.trainer
    inference_buffer = state.inference_buffer
    past_len = config.past_len
    future_len = config.future_len

    if len(inference_buffer) < past_len:
        await broadcast(state, "prediction", {
            "error": f"not enough data ({len(inference_buffer)}/{past_len})"
        })
        return

    # Update predictor model path
    path = getattr(trainer, "latest_sampler_path", None)
    if path:
        predictor.model_path = path

    sampling_client = trainer.sampling_client

    # Capture cutoff timestamp (exclude events after request)
    cutoff_ts = time.time()

    # Filter buffer for items before cutoff
    filtered = [
        item for item in inference_buffer
        if datetime.strptime(item["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp() < cutoff_ts
    ]

    if len(filtered) < past_len:
        await broadcast(state, "prediction", {
            "error": f"not enough pre-cutoff items ({len(filtered)}/{past_len})"
        })
        return

    snapshot = filtered[-past_len:]

    # Run prediction in thread pool
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            lambda: predictor.predict_from_snapshot(
                snapshot, future_len,
                sampling_client=sampling_client,
                num_imgs_per_sample=config.num_imgs_per_sample,
            ),
        )
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        await broadcast(state, "prediction", {"error": str(e)})
        return

    # Broadcast prediction
    await broadcast(state, "prediction", {
        "actions": result["actions"],
        "think": result.get("think", ""),
        "revise": result.get("revise", ""),
        "timestamp": result.get("timestamp", ""),
    })

    # Schedule background eval scoring
    actions_parsed = bool(re.search(r"<action>", result["actions"]))
    if actions_parsed:
        asyncio.create_task(_score_prediction(
            state, result, len(inference_buffer), future_len
        ))


async def _score_prediction(state: Any, result: dict, buffer_pos: int, future_len: int):
    """Background task: wait for enough ground truth, then score the prediction."""
    from powernap.server.ws.handler import broadcast
    from powernap.longnap.trainer_utils import build_actions_block

    # Wait for enough future items to accumulate
    for _ in range(120):  # 2 minute timeout
        if len(state.inference_buffer) >= buffer_pos + future_len:
            break
        await asyncio.sleep(1.0)
    else:
        logger.warning("Score timeout: not enough future items")
        return

    ground_truth = build_actions_block(
        state.inference_buffer[buffer_pos:buffer_pos + future_len]
    )

    config = state.config
    predictor = state.predictor

    loop = asyncio.get_running_loop()
    try:
        reward = await loop.run_in_executor(
            _executor,
            lambda: predictor.score_prediction(
                result["actions"], ground_truth, config.reward_llm
            ),
        )
    except Exception as e:
        logger.warning(f"Score prediction failed: {e}")
        return

    score_data = {
        "reward": reward,
        "accuracy": 0.0,
        "formatting": 0.0,
        "penalty": 0.0,
    }

    # If reward is a dict (from RewardScorer), extract components
    if isinstance(reward, dict):
        score_data = reward

    state.latest_scores = score_data

    await broadcast(state, "score", score_data)
    logger.info(f"Prediction scored: {score_data}")
