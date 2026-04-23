"""FastAPI application with CORS, lifespan, and route registration."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.state import ServerState
from server.routes import settings, status, events
from server.routes.auth import router as auth_router
from server.routes.onboarding import router as onboarding_router
from server.routes.completions import router as completions_router
from connectors.routes import router as connectors_router
from user_models.routes import router as user_models_router
from server.services import start_services, _log_startup_failure

from apps.memory.routes import router as memory_router
from apps.moments.routes import router as moments_router
from apps.seeker.routes import router as seeker_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared state on startup, clean up on shutdown."""

    state = ServerState()
    state.config.load_persisted()
    app.state.server = state

    # If onboarding already done, start services in the background so the
    # HTTP server begins accepting requests (e.g. /api/status) immediately.
    if state.config.onboarding_complete:
        state._startup_task = asyncio.create_task(start_services(state))
        state._startup_task.add_done_callback(_log_startup_failure)

    yield

    # Graceful shutdown
    state = app.state.server

    # If services are still initializing, wait for that to finish first
    startup_task = getattr(state, "_startup_task", None)
    if startup_task and not startup_task.done():
        startup_task.cancel()
        try:
            await startup_task
        except (asyncio.CancelledError, Exception):
            pass

    # Stop Tabracadabra first (synchronous, quick)
    if state.tabracadabra_service is not None:
        try:
            state.tabracadabra_service.stop()
        except Exception:
            logger.warning("Error stopping Tabracadabra service", exc_info=True)

    state.model.training_resumed.clear()

    all_tasks = [
        state.model.training_task,
        state.context_logging_task,
        state.memory_task,
        state.moments_scheduler_task,
        state.moments_discovery_task,
        state.seeker_scheduler_task,
        state.prediction_loop_task,
        state.cost_logger_task,
    ]
    for task in all_tasks:
        if task and not task.done():
            task.cancel()

    # Wait for tasks to actually stop before touching connectors
    await asyncio.gather(
        *[t for t in all_tasks if t],
        return_exceptions=True,
    )

    # Stop DataManager watchdog
    if state.model.data_manager is not None:
        state.model.data_manager.stop()

    # Stop all connectors so child MCP subprocesses are disconnected on shutdown.
    for connector in state.connectors.values():
        connector.stop()
    await asyncio.gather(
        *[connector.disconnect_if_needed() for connector in state.connectors.values()],
        return_exceptions=True,
    )

    logger.info("Tada server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Tada Server", lifespan=lifespan)

    # CORS — allow Electron client from any origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register REST + SSE routes
    app.include_router(auth_router)
    app.include_router(onboarding_router)
    app.include_router(completions_router)
    app.include_router(connectors_router)
    app.include_router(memory_router)
    app.include_router(moments_router)
    app.include_router(seeker_router)
    app.include_router(settings.router)
    app.include_router(status.router)
    app.include_router(user_models_router)
    app.include_router(events.router)

    return app
