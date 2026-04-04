"""GET/PUT /api/settings — API keys and model config."""

import logging
import os
import sys

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdate(BaseModel):
    default_llm_api_key: str | None = None
    tinker_api_key: str | None = None
    hf_token: str | None = None
    wandb_api_key: str | None = None
    model: str | None = None
    reward_llm: str | None = None
    reward_llm_api_key: str | None = None
    label_model: str | None = None
    label_model_api_key: str | None = None
    filter_model: str | None = None
    filter_model_api_key: str | None = None
    fps: int | None = None
    num_generations: int | None = None
    learning_rate: float | None = None
    batch_size: int | None = None
    past_len: int | None = None
    future_len: int | None = None
    loss_mode: str | None = None
    moments_enabled: bool | None = None
    moments_agent_model: str | None = None
    moments_agent_model_api_key: str | None = None
    tabracadabra_enabled: bool | None = None
    tabracadabra_model: str | None = None
    tabracadabra_api_key: str | None = None


@router.get("/settings")
async def get_settings(request: Request):
    state = request.app.state.server
    cfg = state.config
    return {
        "default_llm_api_key": cfg.default_llm_api_key,
        "tinker_api_key": cfg.tinker_api_key,
        "hf_token": cfg.hf_token,
        "wandb_api_key": cfg.wandb_api_key,
        "model": cfg.model,
        "reward_llm": cfg.reward_llm,
        "reward_llm_api_key": cfg.reward_llm_api_key,
        "label_model": cfg.label_model,
        "label_model_api_key": cfg.label_model_api_key,
        "filter_model": cfg.filter_model,
        "filter_model_api_key": cfg.filter_model_api_key,
        "fps": cfg.fps,
        "num_generations": cfg.num_generations,
        "learning_rate": cfg.learning_rate,
        "batch_size": cfg.batch_size,
        "past_len": cfg.past_len,
        "future_len": cfg.future_len,
        "loss_mode": cfg.loss_mode,
        "moments_enabled": cfg.moments_enabled,
        "moments_agent_model": cfg.moments_agent_model,
        "moments_agent_model_api_key": cfg.moments_agent_model_api_key,
        "tabracadabra_enabled": cfg.tabracadabra_enabled,
        "tabracadabra_model": cfg.tabracadabra_model,
        "tabracadabra_api_key": cfg.tabracadabra_api_key,
    }


@router.put("/settings")
async def update_settings(update: SettingsUpdate, request: Request):
    state = request.app.state.server
    cfg = state.config
    updated = []

    for field_name, value in update.model_dump(exclude_none=True).items():
        setattr(cfg, field_name, value)
        updated.append(field_name)

        # Also set environment variables for API keys
        env_map = {
            "default_llm_api_key": "GEMINI_API_KEY",
            "tinker_api_key": "TINKER_API_KEY",
            "hf_token": "HF_TOKEN",
            "wandb_api_key": "WANDB_API_KEY",
        }
        if field_name in env_map:
            os.environ[env_map[field_name]] = value

    cfg.save()

    # Live stop/start tabracadabra service when toggled
    if "tabracadabra_enabled" in updated and sys.platform == "darwin":
        if cfg.tabracadabra_enabled:
            # Start if not already running
            if state.tabracadabra_service is None:
                try:
                    from apps.tabracadabra.main import TabracadabraService, load_prompt

                    tab_config = {
                        "model": cfg.tabracadabra_model,
                        "api_key": cfg.tabracadabra_api_key or cfg.default_llm_api_key,
                        "powernap_base_url": f"http://localhost:{os.environ.get('POWERNAP_PORT', '8000')}",
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

    return {"status": "ok", "updated": updated}
