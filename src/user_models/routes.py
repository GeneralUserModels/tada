"""User model routes — training and inference control.

Registered by server/app.py under /api/user_models.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user_models", tags=["user_models"])


# ── Training ───────────────────────────────────────────────────

@router.post("/training/start")
async def start_training(request: Request):
    model = request.app.state.server.model

    if model.training_active:
        return {"status": "already_active"}

    model.training_resumed.set()
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


# ── Prediction ─────────────────────────────────────────────────

@router.post("/prediction")
async def request_prediction(request: Request):
    state = request.app.state.server
    from user_models.inference import handle_prediction_request
    await handle_prediction_request(state)
    return {"status": "ok"}


@router.get("/latest_prediction")
async def get_latest_prediction(request: Request):
    model = request.app.state.server.model
    if model.latest_prediction is None:
        return {"available": False}
    return {"available": True, **model.latest_prediction}


# ── History ────────────────────────────────────────────────────

@router.get("/history")
async def get_training_history(request: Request):
    state = request.app.state.server
    metrics_path = Path(state.config.log_dir) / "metrics.jsonl"
    if not metrics_path.exists():
        return []
    lines = metrics_path.read_text().strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]
