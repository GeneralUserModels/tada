"""FastAPI application with CORS, lifespan, and route registration."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.state import ServerState
from server.feature_flags import is_enabled
from server.routes import settings, status, events
from server.routes.auth import router as auth_router, refresh_expired_tokens, run_token_refresh
from server.routes.onboarding import router as onboarding_router
from server.routes.completions import router as completions_router
from connectors.routes import router as connectors_router
from user_models.routes import router as user_models_router

from connectors.service import run_context_logging_service
from user_models.training import init_model, run_training_service
from apps.tabracadabra.prediction_loop import run_prediction_loop
from server.cost_tracker import init_cost_tracking, run_cost_logger
from user_models.data_manager import DataManager

from apps.memory.routes import router as memory_router
from apps.moments.routes import router as moments_router
from apps.seeker.routes import router as seeker_router

logger = logging.getLogger(__name__)


async def start_services(state: ServerState) -> None:
    """Start all heavy background services. Called once after onboarding completes."""
    if state.services_started or state._services_starting:
        return
    state._services_starting = True

    # LLM cost tracking (must be before any litellm calls)
    cost_tracker = init_cost_tracking()
    state.cost_logger_task = asyncio.create_task(run_cost_logger(cost_tracker))

    # DataManager
    dm = DataManager(log_dir=state.config.log_dir)
    await dm.start()
    state.model.data_manager = dm
    logger.info("DataManager started")

    # Refresh expired OAuth tokens before connectors start polling
    refresh_expired_tokens(state)

    # Context logging service (creates and owns all connectors)
    state.context_logging_task = asyncio.create_task(run_context_logging_service(state))

    # Mark services as ready as soon as connectors are populated —
    # the frontend needs this before it can show connector status.
    # Remaining services (model, tabracadabra, etc.) continue in the background.
    await state.connectors_ready.wait()
    state.services_started = True

    # Background OAuth token refresh
    state.token_refresh_task = asyncio.create_task(run_token_refresh(state))

    # Memory wiki service
    if is_enabled(state.config, "memory") and state.config.memory_enabled:
        from apps.memory.service import run_memory_service
        state.memory_task = asyncio.create_task(run_memory_service(state))

    # Moments services
    if is_enabled(state.config, "moments") and state.config.moments_enabled:
        from apps.moments.scheduler import run_moments_scheduler
        from apps.moments.discovery import run_moments_discovery
        state.moments_scheduler_task = asyncio.create_task(run_moments_scheduler(state))
        state.moments_discovery_task = asyncio.create_task(run_moments_discovery(state))

    # Seeker service
    if is_enabled(state.config, "seeker") and state.config.seeker_enabled:
        from apps.seeker.scheduler import run_seeker_scheduler
        state.seeker_scheduler_task = asyncio.create_task(run_seeker_scheduler(state))

    # Initialize predictor and start training loop
    await init_model(state)
    state.model.training_task = asyncio.create_task(run_training_service(state))
    logger.info("Training service started (%s mode)", state.config.model_type)

    # Tabracadabra event tap service (macOS only)
    if sys.platform == "darwin" and is_enabled(state.config, "tabracadabra") and state.config.tabracadabra_enabled:
        state.prediction_loop_task = asyncio.create_task(run_prediction_loop(state))
        try:
            from apps.tabracadabra.main import TabracadabraService, load_prompt

            config = {
                "model": state.config.tabracadabra_model,
                "api_key": state.config.resolve_api_key("tabracadabra_api_key"),
                "tada_base_url": f"http://localhost:{os.environ.get('TADA_PORT', '8000')}",
            }
            service = TabracadabraService(config=config, prompt_text=load_prompt())
            service.start()
            state.tabracadabra_service = service
        except Exception:
            logger.warning("Tabracadabra service failed to start", exc_info=True)

    logger.info("Tada server started")


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
        state.token_refresh_task,
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
