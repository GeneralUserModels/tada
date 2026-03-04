"""POST /api/control/* — start/stop recording, training, inference."""

import asyncio
import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/control", tags=["control"])


# ── Recording ──────────────────────────────────────────────────

@router.post("/recording/start")
async def start_recording(request: Request):
    state = request.app.state.server

    if state.recording_active:
        return {"status": "already_active"}

    state.recording_active = True
    state.recording_resumed.set()

    # Only create a new task if one isn't already running (paused)
    if state.labeling_task is None or state.labeling_task.done():
        from powernap.server.services.labeling import run_labeling_service
        state.labeling_task = asyncio.create_task(run_labeling_service(state))

    logger.info("Recording started")
    return {"status": "ok"}


@router.post("/recording/stop")
async def stop_recording(request: Request):
    state = request.app.state.server

    if not state.recording_active:
        return {"status": "not_active"}

    state.recording_active = False
    state.recording_resumed.clear()

    logger.info("Recording stopped (labeling task stays alive)")
    return {"status": "ok"}


# ── Training ───────────────────────────────────────────────────

@router.post("/training/start")
async def start_training(request: Request):
    state = request.app.state.server

    if state.training_active:
        return {"status": "already_active"}

    state.training_active = True
    state.training_resumed.set()

    # Only create a new task if one isn't already running
    if state.training_task is None or state.training_task.done():
        from powernap.server.services.training import run_training_service
        state.training_task = asyncio.create_task(run_training_service(state))

    logger.info("Training started")
    return {"status": "ok"}


@router.post("/training/stop")
async def stop_training(request: Request):
    state = request.app.state.server

    if not state.training_active:
        return {"status": "not_active"}

    state.training_active = False
    state.training_resumed.clear()

    logger.info("Training stopped")
    return {"status": "ok"}


# ── Inference ──────────────────────────────────────────────────

@router.post("/inference/start")
async def start_inference(request: Request):
    state = request.app.state.server

    if state.inference_active:
        return {"status": "already_active"}

    state.inference_active = True
    logger.info("Inference enabled")
    return {"status": "ok"}


@router.post("/inference/stop")
async def stop_inference(request: Request):
    state = request.app.state.server

    if not state.inference_active:
        return {"status": "not_active"}

    state.inference_active = False
    logger.info("Inference disabled")
    return {"status": "ok"}
