"""FastAPI application with CORS, lifespan, and route registration."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.state import ServerState
from server.routes import settings, status, events
from server.routes.auth import router as auth_router, refresh_google_tokens, refresh_outlook_tokens
from server.routes.onboarding import router as onboarding_router
from connectors.routes import router as connectors_router
from user_models.routes import router as user_models_router
from connectors.service import run_context_logging_service
from user_models.training import init_model, run_training_service
from apps.tabracadabra.prediction_loop import run_prediction_loop
from server.cost_tracker import init_cost_tracking, run_cost_logger

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared state on startup, clean up on shutdown."""

    state = ServerState()
    state.config.load_persisted()

    # Start LLM cost tracking (must be before any litellm calls)
    cost_tracker = init_cost_tracking()
    state.cost_logger_task = asyncio.create_task(run_cost_logger(cost_tracker))

    # Auto-start DataManager so label counts are available immediately
    from user_models.data_manager import DataManager
    dm = DataManager(log_dir=state.config.log_dir)
    await dm.start()
    state.model.data_manager = dm
    logger.info("DataManager started")

    # Start context logging service (creates and owns all connectors)
    state.context_logging_task = asyncio.create_task(run_context_logging_service(state))

    # Background OAuth token refresh (every 45 min, no-ops if no token)
    state.google_refresh_task = asyncio.create_task(refresh_google_tokens(state.config))
    state.outlook_refresh_task = asyncio.create_task(refresh_outlook_tokens(state.config))

    # Start moments services (scheduler + periodic discovery)
    from apps.moments.scheduler import run_moments_scheduler
    from apps.moments.discovery import run_moments_discovery
    state.moments_scheduler_task = asyncio.create_task(run_moments_scheduler(state))
    state.moments_discovery_task = asyncio.create_task(run_moments_discovery(state))
    # Initialize predictor (and trainer for powernap) before starting loops
    await init_model(state)
    state.model.training_task = asyncio.create_task(run_training_service(state))
    logger.info("Training service started (%s mode)", state.config.model_type)

    # Start Tabracadabra event tap service (macOS only)
    if sys.platform == "darwin" and state.config.tabracadabra_enabled:
        # Background prediction loop (keeps tabracadabra context cache warm)
        state.prediction_loop_task = asyncio.create_task(run_prediction_loop(state))
        try:
            from apps.tabracadabra.main import TabracadabraService, load_prompt

            config = {
                "model": state.config.tabracadabra_model,
                "api_key": state.config.tabracadabra_api_key or state.config.default_llm_api_key,
                "powernap_base_url": f"http://localhost:{os.environ.get('POWERNAP_PORT', '8000')}",
            }
            service = TabracadabraService(config=config, prompt_text=load_prompt())
            service.start()
            state.tabracadabra_service = service
        except Exception:
            logger.warning("Tabracadabra service failed to start", exc_info=True)

    app.state.server = state
    logger.info("PowerNap server started")
    yield

    # Graceful shutdown
    state = app.state.server

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
        state.google_refresh_task,
        state.outlook_refresh_task,
        state.moments_scheduler_task,
        state.moments_discovery_task,
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
    await asyncio.gather(
        *[connector.stop() for connector in state.connectors.values()],
        return_exceptions=True,
    )

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

    # Register REST + SSE routes
    app.include_router(auth_router)
    app.include_router(onboarding_router)
    app.include_router(connectors_router)
    from apps.moments.routes import router as moments_router
    app.include_router(moments_router)
    app.include_router(settings.router)
    app.include_router(status.router)
    app.include_router(user_models_router)
    app.include_router(events.router)

    return app
