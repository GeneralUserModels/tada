"""FastAPI application with CORS, lifespan, and route registration."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from server.state import ServerState
from server.routes import connectors, control, settings, status, training
from server.ws.handler import ws_endpoint
from server.services.context_logging import run_context_logging_service

logger = logging.getLogger(__name__)


def _restore_context_from_disk(state: ServerState) -> None:
    """Seed context_buffer and labels_processed from persisted JSONL files."""
    log_dir = Path(state.config.log_dir)

    all_entries = []
    for jsonl_path in log_dir.glob("*/filtered.jsonl"):
        for line in jsonl_path.read_text().splitlines():
            if line.strip():
                all_entries.append(json.loads(line))

    all_entries.sort(key=lambda e: e["timestamp"])

    state.context_buffer = [{
        "timestamp": e["timestamp"],
        "text": e["text"],
        "source": e["source_name"],
        "prediction_event": e["prediction_event"],
        "img_path": e["source"].get("screenshot_path") if e["prediction_event"] else None,
    } for e in all_entries]

    state.labels_processed = sum(1 for e in all_entries if e["prediction_event"])
    logger.info(f"Restored {len(state.context_buffer)} entries, {state.labels_processed} total labels")



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared state on startup, clean up on shutdown."""

    state = ServerState()
    state.config.load_persisted()
    _restore_context_from_disk(state)

    # Start context logging service (creates and owns all connectors)
    state.context_logging_task = asyncio.create_task(run_context_logging_service(state))

    app.state.server = state
    logger.info("PowerNap server started")
    yield

    # Graceful shutdown: cancel running services
    state = app.state.server
    state.recording_active = False
    state.training_active = False
    state.inference_active = False

    for task in [state.training_task, state.context_logging_task]:
        if task and not task.done():
            task.cancel()

    # Wait for tasks to actually stop before touching connectors
    await asyncio.gather(
        *[t for t in [state.training_task, state.context_logging_task] if t],
        return_exceptions=True,
    )

    # Pause all connectors (stops active ones like filesystem watcher)
    for connector in state.connectors.values():
        connector.pause()

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
    app.include_router(connectors.router)
    app.include_router(control.router)
    app.include_router(settings.router)
    app.include_router(status.router)
    app.include_router(training.router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_route(websocket: WebSocket):
        await ws_endpoint(websocket, websocket.app.state.server)

    return app
