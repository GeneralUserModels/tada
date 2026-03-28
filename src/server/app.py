"""FastAPI application with CORS, lifespan, and route registration."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from server.state import ServerState
from server.routes import connectors, control, moments, settings, status, training
from server.ws.handler import ws_endpoint
from server.services.context_logging import _load_img, run_context_logging_service

logger = logging.getLogger(__name__)

def _get_last_trained_end_ts(log_dir: Path) -> float:
    """Return the end_ts of the last checkpoint entry."""
    ckpt_file = log_dir / "checkpoints.jsonl"
    if not ckpt_file.exists():
        return 0.0
    lines = [l for l in ckpt_file.read_text().strip().splitlines() if l.strip()]
    if not lines:
        return 0.0
    return json.loads(lines[-1]).get("end_ts", 0)


def _restore_context_from_disk(state: ServerState) -> None:
    """Seed context_buffer and labels_processed from persisted JSONL files.

    Only loads entries newer than the last checkpoint's end_ts so training
    doesn't repeat samples the model has already seen.
    """
    log_dir = Path(state.config.log_dir)
    cutoff_ts = _get_last_trained_end_ts(log_dir)

    all_entries = []
    for jsonl_path in log_dir.glob("*/filtered.jsonl"):
        for line in jsonl_path.read_text().splitlines():
            entry = json.loads(line)
            all_entries.append(entry)

    all_entries.sort(key=lambda e: e["timestamp"])

    entries = []
    for entry in all_entries:
        ts = entry["timestamp"]
        img = _load_img(entry["source"]["screenshot_path"]) if (entry["prediction_event"] and ts > cutoff_ts) else None
        entries.append({
            "timestamp": ts,
            "text": entry["text"],
            "source": entry["source_name"],
            "prediction_event": entry["prediction_event"],
            "img": img,
        })

    training_entries = [e for e in entries if e["timestamp"] > cutoff_ts][-2000:]
    state.context_buffer = training_entries
    state.labels_processed = sum(1 for e in entries if e["prediction_event"])
    logger.info(f"Restored {len(training_entries)} training entries (cutoff={cutoff_ts:.0f}), {state.labels_processed} total labels")

def _restore_step_from_checkpoint(state: ServerState) -> None:
    """Seed state.step_count from the checkpoint entry in checkpoints.jsonl."""
    checkpoint_path = state.config.resume_from_checkpoint
    log_dir = state.config.log_dir
    ckpt_file = Path(log_dir) / "checkpoints.jsonl"

    if not ckpt_file.exists():
        logger.warning(f"No checkpoints.jsonl found in {log_dir}")
        return

    lines = ckpt_file.read_text().splitlines()
    entries = [json.loads(l) for l in lines]

    # Resolve "auto" → last checkpoint's state_path
    resolved = entries[-1]["state_path"] if checkpoint_path == "auto" else checkpoint_path

    entry = next(e for e in entries if e["state_path"] == resolved)
    state.step_count = entry["step"]
    logger.info(f"Restored step count {state.step_count} from checkpoint")

    logger.warning(f"No checkpoint entry found for {resolved}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared state on startup, clean up on shutdown."""

    state = ServerState()
    state.config.load_persisted()
    _restore_context_from_disk(state)
    if state.config.resume_from_checkpoint:
        _restore_step_from_checkpoint(state)

    # Start context logging service (creates and owns all connectors)
    state.context_logging_task = asyncio.create_task(run_context_logging_service(state))

    # Start moments services (scheduler + periodic discovery)
    from server.services.moments_scheduler import run_moments_scheduler
    from server.services.moments_discovery import run_moments_discovery
    state.moments_scheduler_task = asyncio.create_task(run_moments_scheduler(state))
    state.moments_discovery_task = asyncio.create_task(run_moments_discovery(state))

    app.state.server = state
    logger.info("PowerNap server started")
    yield

    # Graceful shutdown: cancel running services
    state = app.state.server
    state.recording_active = False
    state.training_active = False
    state.inference_active = False

    for task in [state.training_task, state.context_logging_task,
                 state.moments_scheduler_task, state.moments_discovery_task]:
        if task and not task.done():
            task.cancel()

    # Wait for tasks to actually stop before touching connectors
    await asyncio.gather(
        *[t for t in [state.training_task, state.context_logging_task,
                     state.moments_scheduler_task, state.moments_discovery_task] if t],
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
    app.include_router(moments.router)
    app.include_router(settings.router)
    app.include_router(status.router)
    app.include_router(training.router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_route(websocket: WebSocket):
        await ws_endpoint(websocket, websocket.app.state.server)

    return app
