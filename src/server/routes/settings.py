"""GET/PUT /api/settings — API keys and model config."""

import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdate(BaseModel):
    gemini_api_key: str | None = None
    tinker_api_key: str | None = None
    hf_token: str | None = None
    wandb_api_key: str | None = None
    model: str | None = None
    reward_llm: str | None = None
    label_model: str | None = None
    fps: int | None = None
    num_generations: int | None = None
    learning_rate: float | None = None
    batch_size: int | None = None
    past_len: int | None = None
    future_len: int | None = None
    loss_mode: str | None = None


@router.get("/settings")
async def get_settings(request: Request):
    state = request.app.state.server
    cfg = state.config
    return {
        "gemini_api_key": cfg.gemini_api_key,
        "tinker_api_key": cfg.tinker_api_key,
        "hf_token": cfg.hf_token,
        "wandb_api_key": cfg.wandb_api_key,
        "model": cfg.model,
        "reward_llm": cfg.reward_llm,
        "label_model": cfg.label_model,
        "fps": cfg.fps,
        "num_generations": cfg.num_generations,
        "learning_rate": cfg.learning_rate,
        "batch_size": cfg.batch_size,
        "past_len": cfg.past_len,
        "future_len": cfg.future_len,
        "loss_mode": cfg.loss_mode,
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
            "gemini_api_key": "GEMINI_API_KEY",
            "tinker_api_key": "TINKER_API_KEY",
            "hf_token": "HF_TOKEN",
            "wandb_api_key": "WANDB_API_KEY",
        }
        if field_name in env_map:
            os.environ[env_map[field_name]] = value

    cfg.save()
    return {"status": "ok", "updated": updated}
