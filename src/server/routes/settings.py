"""GET/PUT /api/settings — API keys and model config."""

import asyncio
import logging
import os
import sys
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import create_model

from server.config import ServerConfig, SETTINGS_API_FIELDS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])

# Auto-generate SettingsUpdate from ServerConfig's field definitions so the
# field list is never duplicated.  Each field becomes Optional[T] = None.
_update_fields: dict = {}
for _name, _info in ServerConfig.model_fields.items():
    if _name in SETTINGS_API_FIELDS:
        _update_fields[_name] = (Optional[_info.annotation], None)

SettingsUpdate = create_model("SettingsUpdate", **_update_fields)


@router.get("/settings")
async def get_settings(request: Request):
    state = request.app.state.server
    cfg = state.config
    return {f: getattr(cfg, f) for f in SETTINGS_API_FIELDS}


@router.put("/settings")
async def update_settings(update: SettingsUpdate, request: Request):
    state = request.app.state.server
    cfg = state.config
    updated = []

    for field_name, value in update.model_dump(exclude_none=True).items():
        setattr(cfg, field_name, value)
        updated.append(field_name)

    cfg.save()

    # Live stop/start tabracadabra service when toggled
    if "tabracadabra_enabled" in updated and sys.platform == "darwin":
        if cfg.tabracadabra_enabled:
            # Start if not already running
            if state.tabracadabra_service is None:
                try:
                    from apps.tabracadabra.main import TabracadabraService, load_prompt
                    from apps.tabracadabra.prediction_loop import run_prediction_loop

                    if state.prediction_loop_task is None or state.prediction_loop_task.done():
                        state.prediction_loop_task = asyncio.create_task(run_prediction_loop(state))

                    tab_config = {
                        "model": cfg.tabracadabra_model,
                        "api_key": cfg.resolve_api_key("tabracadabra_api_key"),
                        "tada_base_url": f"http://localhost:{os.environ.get('TADA_PORT', '8000')}",
                    }
                    service = TabracadabraService(config=tab_config, prompt_text=load_prompt())
                    service.start()
                    state.tabracadabra_service = service
                    logger.info("Tabracadabra service started via settings")
                except Exception:
                    logger.warning("Failed to start Tabracadabra service", exc_info=True)
        else:
            # Stop if running
            if state.tabracadabra_service is not None:
                try:
                    state.tabracadabra_service.stop()
                    logger.info("Tabracadabra service stopped via settings")
                except Exception:
                    logger.warning("Error stopping Tabracadabra service", exc_info=True)
                state.tabracadabra_service = None
            if state.prediction_loop_task is not None and not state.prediction_loop_task.done():
                state.prediction_loop_task.cancel()
                state.prediction_loop_task = None

    return {"status": "ok", "updated": updated}
