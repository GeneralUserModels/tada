"""User model routes — training and inference control.

Registered by server/app.py under /api/user_models.
"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user_models", tags=["user_models"])


# ── Training ───────────────────────────────────────────────────

@router.post("/training/start")
async def start_training(request: Request):
    state = request.app.state.server
    model = state.model

    if model.training_active:
        return {"status": "already_active"}

    model.training_resumed.set()

    if model.training_task is None or model.training_task.done():
        from user_models.training import run_training_service
        model.training_task = asyncio.create_task(run_training_service(state))
        model.training_task.add_done_callback(
            lambda t: logger.error("Training task crashed: %s", t.exception()) if not t.cancelled() and t.exception() else None
        )

    logger.info("Training started")
    return {"status": "ok"}


@router.post("/training/stop")
async def stop_training(request: Request):
    model = request.app.state.server.model

    if not model.training_active:
        return {"status": "not_active"}

    model.training_resumed.clear()

    logger.info("Training stopped")
    return {"status": "ok"}


# ── Inference ──────────────────────────────────────────────────

@router.post("/inference/start")
async def start_inference(request: Request):
    state = request.app.state.server
    model = state.model

    if model.inference_active:
        return {"status": "already_active"}

    model.inference_active = True

    # For prompted mode, auto-initialize predictor and start label watcher
    if state.config.model_type != "powernap":
        model.training_resumed.set()
        if model.training_task is None or model.training_task.done():
            from user_models.training import run_training_service
            model.training_task = asyncio.create_task(run_training_service(state))
            model.training_task.add_done_callback(
                lambda t: logger.error("Label watcher crashed: %s", t.exception()) if not t.cancelled() and t.exception() else None
            )

    logger.info("Inference enabled")
    return {"status": "ok"}


@router.post("/inference/stop")
async def stop_inference(request: Request):
    model = request.app.state.server.model

    if not model.inference_active:
        return {"status": "not_active"}

    model.inference_active = False
    logger.info("Inference disabled")
    return {"status": "ok"}


# ── Prediction ─────────────────────────────────────────────────

@router.post("/prediction")
async def request_prediction(request: Request):
    state = request.app.state.server
    from user_models.inference import handle_prediction_request
    await handle_prediction_request(state)
    return {"status": "ok"}


# ── History ────────────────────────────────────────────────────

@router.get("/history")
async def get_training_history(request: Request):
    state = request.app.state.server
    metrics_path = Path(state.config.log_dir) / "metrics.jsonl"
    if not metrics_path.exists():
        return []
    lines = metrics_path.read_text().strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]
