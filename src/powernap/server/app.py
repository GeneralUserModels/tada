"""FastAPI application with CORS, lifespan, and route registration."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from powernap.server.state import ServerState
from powernap.server.routes import control, recordings, settings, status, training
from powernap.server.ws.handler import ws_endpoint

logger = logging.getLogger(__name__)


def _restore_step_from_checkpoint(state: ServerState) -> None:
    """Seed state.step_count from the checkpoint entry in checkpoints.jsonl."""
    checkpoint_path = state.config.resume_from_checkpoint
    log_dir = state.config.log_dir
    ckpt_file = Path(log_dir) / "checkpoints.jsonl"

    if not ckpt_file.exists():
        logger.warning(f"No checkpoints.jsonl found in {log_dir}")
        return

    # Resolve "auto" → last checkpoint's state_path
    resolved = checkpoint_path
    if checkpoint_path == "auto":
        last = None
        for line in ckpt_file.read_text().strip().splitlines():
            entry = json.loads(line)
            if "state_path" in entry:
                last = entry
        if not last:
            logger.warning("No valid checkpoints found in checkpoints.jsonl")
            return
        resolved = last["state_path"]
        logger.info(f"Auto-resolved checkpoint: {resolved}")

    # Look up the entry for the resolved path to get the step count
    for line in ckpt_file.read_text().strip().splitlines():
        entry = json.loads(line)
        if entry.get("state_path") == resolved:
            state.step_count = entry.get("step", 0)
            logger.info(f"Restored step count {state.step_count} from checkpoint")
            return

    logger.warning(f"No checkpoint entry found for {resolved}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared state on startup, clean up on shutdown."""
    from connectors.filesystem.watcher import FilesystemWatcher
    from powernap.server.services.context_logging import run_context_logging_service

    state = ServerState()
    if state.config.resume_from_checkpoint:
        _restore_step_from_checkpoint(state)

    # Start filesystem watcher
    fs_watcher = FilesystemWatcher()
    fs_watcher.start()
    state.filesystem_watcher = fs_watcher

    # Start context logging service
    state.context_logging_task = asyncio.create_task(run_context_logging_service(state))

    app.state.server = state
    logger.info("PowerNap server started")
    yield

    # Graceful shutdown: cancel running services
    state = app.state.server
    state.recording_active = False
    state.training_active = False
    state.inference_active = False

    for task in [state.labeling_task, state.training_task, state.context_logging_task]:
        if task and not task.done():
            task.cancel()

    # Stop filesystem watcher
    if state.filesystem_watcher:
        state.filesystem_watcher.stop()

    # Close all WebSocket connections
    for ws in list(state.ws_connections):
        try:
            await ws.close()
        except Exception:
            pass

    logger.info("PowerNap server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="PowerNap Server", lifespan=lifespan)

    # CORS — allow Electron client from any origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register REST routes
    app.include_router(control.router)
    app.include_router(recordings.router)
    app.include_router(settings.router)
    app.include_router(status.router)
    app.include_router(training.router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_route(websocket: WebSocket):
        await ws_endpoint(websocket, websocket.app.state.server)

    return app
