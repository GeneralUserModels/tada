"""Heavy background service orchestration — started once after onboarding."""

import asyncio
import logging
import os
import sys

from server.state import ServerState
from server.feature_flags import is_enabled
from server.routes.auth import refresh_expired_tokens
from connectors.service import run_context_logging_service
from user_models.training import init_model, run_training_service
from server.cost_tracker import init_cost_tracking, run_cost_logger
from user_models.data_manager import DataManager

logger = logging.getLogger(__name__)


def _log_startup_failure(task: asyncio.Task) -> None:
    """Surface exceptions from start_services so dead schedulers don't go unnoticed."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("start_services failed — background services are not running", exc_info=exc)


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

    # Tabracadabra event tap goes up AFTER init_model. Installing the tap earlier
    # lets the user fire Option+Tab while init_model is still hammering the GIL —
    # which makes Quartz event posts (CGEventPost / unicode insert) crawl, so the
    # spinner redraws take 250+ms instead of 2ms. Holding the tap until init_model
    # is done means the first Option+Tab is also the first snappy one, and the
    # "Getting ready" checklist in onboarding stays honest: the box ticks when the
    # system is actually calm.
    if sys.platform == "darwin" and is_enabled(state.config, "tabracadabra") and state.config.tabracadabra_enabled:
        try:
            from apps.tabracadabra.main import TabracadabraService, load_prompt

            config = {
                "model": state.config.tabracadabra_model,
                "api_key": state.config.resolve_api_key("tabracadabra_api_key"),
                "tada_base_url": f"http://localhost:{os.environ.get('TADA_PORT', '8000')}",
            }
            service = TabracadabraService(config=config, prompt_text=load_prompt(state.config.log_dir))
            service.start()
            state.tabracadabra_service = service
        except Exception:
            logger.warning("Tabracadabra service failed to start", exc_info=True)

    logger.info("Tada server started")
