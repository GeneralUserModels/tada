"""Heavy background service orchestration — started once after onboarding."""

import asyncio
import logging
import os
import sys
import time

from server.state import ServerState
from server.feature_flags import is_enabled
from server.routes.auth import refresh_expired_tokens
from connectors.service import run_context_logging_service
from user_models.training import init_model, run_training_service
from server.cost_tracker import init_cost_tracking, run_cost_logger
from user_models.data_manager import DataManager
from connectors.screen.napsack.recorder import SCREEN_FRAME_HEARTBEAT

logger = logging.getLogger(__name__)

# Mirrors the freshness threshold in /api/services/status so the server-side
# wait matches what the renderer's "Getting ready" screen considers ready.
_BOOT_FRAME_FRESH_S = 5.0


def _log_startup_failure(task: asyncio.Task) -> None:
    """Surface exceptions from start_services so dead schedulers don't go unnoticed."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("start_services failed — background services are not running", exc_info=exc)


async def _wait_for_boot_ready(state: ServerState) -> None:
    """Block until the same conditions the 'Getting ready' screen polls for are
    satisfied: tabracadabra event tap is live (when enabled) and a fresh screen
    frame exists (when the screen connector is enabled).

    Anything that runs an LLM/agent (init_model, training, memory/moments/seeker
    schedulers) is gated on this so no Claude calls happen while the user is
    still on the boot screen — those calls would compete with the work that
    actually unblocks it (event tap registration, first screen capture).
    """
    require_tabra = (
        sys.platform == "darwin"
        and is_enabled(state.config, "tabracadabra")
        and state.config.tabracadabra_enabled
    )
    # Read the live connector state, not enabled_connectors: a connector that
    # was paused on app close (toggled off, or error-paused) shouldn't gate boot
    # readiness — no recorder is running, so no frame will ever land.
    screen_conn = state.connectors.get("screen")
    require_screen = screen_conn is not None and not screen_conn.paused

    while True:
        tabra_ok = (
            not require_tabra
            or (state.tabracadabra_service is not None and state.tabracadabra_service.is_ready())
        )
        try:
            screen_ok = (not require_screen) or (
                (time.time() - os.stat(SCREEN_FRAME_HEARTBEAT).st_mtime) < _BOOT_FRAME_FRESH_S
            )
        except OSError:
            screen_ok = not require_screen
        if tabra_ok and screen_ok:
            return
        await asyncio.sleep(0.5)


async def start_services(state: ServerState) -> None:
    """Start all heavy background services. Called once after onboarding completes."""
    if state.services_started or state._services_starting:
        return
    state._services_starting = True

    # Tabracadabra event tap goes up FIRST so the Option+Tab tap is live before
    # any other service competes for resources. The "Getting ready" screen gates
    # on tabracadabra_ready, so starting it ahead of connectors and init_model
    # is what unblocks the boot screen quickly. Spawning the tap is just a
    # daemon-thread start — it doesn't block this coroutine.
    if sys.platform == "darwin" and is_enabled(state.config, "tabracadabra") and state.config.tabracadabra_enabled:
        try:
            from apps.tabracadabra.main import TabracadabraService, load_prompt

            tabra_config = {
                "model": state.config.tabracadabra_model,
                "api_key": state.config.resolve_api_key("tabracadabra_api_key"),
                "tada_base_url": f"http://localhost:{os.environ.get('TADA_PORT', '8000')}",
            }
            service = TabracadabraService(config=tabra_config, prompts=load_prompt(state.config.log_dir))
            service.start()
            state.tabracadabra_service = service
        except Exception:
            logger.warning("Tabracadabra service failed to start", exc_info=True)

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
    await state.connectors_ready.wait()
    state.services_started = True

    # Hold every LLM-using task until the boot screen would clear. init_model
    # (prompted mode runs index_context, which embeds context) and the
    # memory/moments/seeker schedulers all hit Claude — running them while the
    # user still sees "Getting ready" both delays the screen and starts agent
    # work the user hasn't seen the dashboard for yet.
    await _wait_for_boot_ready(state)

    # Initialize predictor and start training loop
    await init_model(state)
    state.model.training_task = asyncio.create_task(run_training_service(state))
    logger.info("Training service started (%s mode)", state.config.model_type)

    if is_enabled(state.config, "memory") and state.config.memory_enabled:
        from apps.memory.service import run_memory_service
        state.memory_task = asyncio.create_task(run_memory_service(state))

    if is_enabled(state.config, "moments") and state.config.moments_enabled:
        from apps.moments.scheduler import run_moments_scheduler
        from apps.moments.discovery import run_moments_discovery
        state.moments_scheduler_task = asyncio.create_task(run_moments_scheduler(state))
        state.moments_discovery_task = asyncio.create_task(run_moments_discovery(state))

    if is_enabled(state.config, "seeker") and state.config.seeker_enabled:
        from apps.seeker.scheduler import run_seeker_scheduler
        state.seeker_scheduler_task = asyncio.create_task(run_seeker_scheduler(state))

    logger.info("Tada server started")
