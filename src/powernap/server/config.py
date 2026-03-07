"""Server configuration — mirrors run_online.py args as a Pydantic model."""

import os

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    # API keys (populated via settings endpoint or env)
    gemini_api_key: str = ""
    tinker_api_key: str = ""
    hf_token: str = ""
    wandb_api_key: str = ""

    # Recorder
    fps: int = 5
    buffer_seconds: int = 120
    precision: str = "accurate"

    # Labeler
    label_model: str = "gemini-3-flash-preview"
    chunk_size: int = 60
    chunk_fps: int = 1
    chunk_workers: int = 4

    # Trainer
    model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"
    reward_llm: str = "gemini/gemini-3-flash-preview"
    num_generations: int = 8
    learning_rate: float = 5e-5
    max_completion_length: int = 512
    num_imgs_per_sample: int = 2
    loss_mode: str = Field(default_factory=lambda: os.getenv("POWERNAP_LOSS_MODE", "llm_judge"))
    eval_with_llm_judge: bool = False
    batch_size: int = 8
    past_len: int = 16
    future_len: int = 8

    # Inference
    predict_every_n_seconds: int = 10

    # Logging
    log_dir: str = Field(default_factory=lambda: os.getenv("POWERNAP_LOG_DIR", "./logs"))
    log_to_wandb: bool = Field(default_factory=lambda: os.getenv("POWERNAP_LOG_TO_WANDB", "") == "1")
    wandb_project: str = Field(default_factory=lambda: os.getenv("POWERNAP_WANDB_PROJECT", "longnap-online"))
    wandb_run_name: str = Field(default_factory=lambda: os.getenv("POWERNAP_WANDB_RUN_NAME", "longnap-online-env"))

    # Recording persistence
    save_recordings: bool = Field(default_factory=lambda: os.getenv("POWERNAP_SAVE_RECORDINGS", "") == "1")

    # Checkpointing
    checkpoint_every_n_steps: int = 2
    resume_from_checkpoint: str | None = Field(default_factory=lambda: os.getenv("POWERNAP_RESUME_FROM_CHECKPOINT") or None)
    retriever_checkpoint: str | None = Field(default_factory=lambda: os.getenv("POWERNAP_RETRIEVER_CHECKPOINT") or None)
    sampler_ttl_seconds: int = 60
