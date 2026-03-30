"""Server configuration — mirrors run_online.py args as a Pydantic model."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

_default_config_path = str(Path.home() / ".config" / "powernap" / "powernap-config.json")
CONFIG_PATH = Path(os.environ.get("POWERNAP_CONFIG_PATH", _default_config_path))

# Fields that are user-settable via the API and persisted to disk.
# CLI-arg fields (log_dir, token paths, etc.) are excluded — they always win.
_PERSISTED_FIELDS = {
    "default_llm_api_key", "tinker_api_key", "hf_token", "wandb_api_key",
    "model", "reward_llm", "reward_llm_api_key",
    "label_model", "label_model_api_key",
    "filter_model", "filter_model_api_key",
    "fps", "num_generations",
    "learning_rate", "batch_size", "past_len", "future_len", "loss_mode",
    "model_type", "prompted_model",
    "disabled_connectors", "connector_errors", "mcp_connectors",
    "onboarding_complete",
}


class MCPConnectorDef(BaseModel):
    """Definition of a community or custom MCP server to use as a powernap connector."""

    name: str
    """Unique connector name (shown in /api/connectors)."""

    command: str
    """Executable to spawn, e.g. 'python', 'npx', 'uvx'."""

    args: list[str] = []
    """Arguments passed to the command, e.g. ['-m', 'connectors.gmail.server']."""

    tool: str
    """Name of the MCP tool to call on each poll, e.g. 'fetch_emails'."""

    interval: int = 300
    """Poll interval in seconds."""

    env: dict[str, str] | None = None
    """Extra environment variables merged into the server process environment."""

    filter: bool = True
    """Whether to run the LLM relevance filter on fetched items."""

    prediction_event: bool = False
    """Whether items from this connector are prediction targets (like screen)."""

    log_subdir: str = ""
    """Log subdirectory name; defaults to the connector name if empty."""

    exclude_from_serialization: list[str] = []
    """Item fields to strip when writing to JSONL (e.g. ['img'] for binary data)."""

    requires_auth: str | None = None
    """Auth group for this connector: 'google', 'outlook', or None."""


class ServerConfig(BaseModel):
    # API keys (populated via settings endpoint or env)
    default_llm_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    tinker_api_key: str = Field(default_factory=lambda: os.getenv("TINKER_API_KEY", ""))
    hf_token: str = Field(default_factory=lambda: os.getenv("HF_TOKEN", ""))
    wandb_api_key: str = Field(default_factory=lambda: os.getenv("WANDB_API_KEY", ""))

    # Recorder
    fps: int = 5
    buffer_seconds: int = 120
    precision: str = "accurate"

    # Labeler
    label_model: str = "gemini/gemini-3-flash-preview"
    label_model_api_key: str = ""
    filter_model: str = "gemini/gemini-3-flash-preview"
    filter_model_api_key: str = ""
    chunk_workers: int = 4

    # Model selection
    model_type: str = Field(default_factory=lambda: os.getenv("POWERNAP_MODEL_TYPE", "prompted"))
    prompted_model: str = Field(default_factory=lambda: os.getenv("POWERNAP_PROMPTED_MODEL", "gemini/gemini-3-flash-preview"))

    # Trainer
    model: str = Field(default_factory=lambda: os.getenv("POWERNAP_MODEL", "Qwen/Qwen3-VL-30B-A3B-Instruct"))
    reward_llm: str = "gemini/gemini-3-flash-preview"
    reward_llm_api_key: str = ""
    num_generations: int = 4
    learning_rate: float = 5e-5
    max_completion_length: int = 512
    num_imgs_per_sample: int | None = None
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

    # Google token path (for Gmail / Calendar connectors)
    google_token_path: str = Field(default_factory=lambda: os.getenv("POWERNAP_GOOGLE_TOKEN_PATH", ""))

    # Outlook token path (for Outlook Email / Calendar connectors)
    outlook_token_path: str = Field(default_factory=lambda: os.getenv("POWERNAP_OUTLOOK_TOKEN_PATH", ""))

    # Recording persistence
    save_recordings: bool = Field(default_factory=lambda: os.getenv("POWERNAP_SAVE_RECORDINGS", "") == "1")

    # Checkpointing
    checkpoint_every_n_steps: int = 2
    resume_from_checkpoint: str | None = Field(default_factory=lambda: os.getenv("POWERNAP_RESUME_FROM_CHECKPOINT") or None)
    retriever_checkpoint: str | None = Field(default_factory=lambda: os.getenv("POWERNAP_RETRIEVER_CHECKPOINT") or None)
    sampler_ttl_seconds: int = 60

    # Connectors: names of connectors that are disabled (paused)
    disabled_connectors: list[str] = Field(default_factory=list)

    # Connector error messages persisted across restarts (name → error string)
    connector_errors: dict[str, str] = Field(default_factory=dict)

    # Community / custom MCP connectors added by the user
    mcp_connectors: list[MCPConnectorDef] = Field(default_factory=list)

    # Onboarding completion flag (set by POST /api/onboarding/complete)
    onboarding_complete: bool = False

    def load_persisted(self) -> None:
        """Load user-settable fields from the config file, if it exists.

        CLI-arg-derived fields (log_dir, token paths, etc.) are not overwritten.
        Also sets env vars for API keys so subprocesses inherit them.
        """
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except Exception:
            return
        for field in _PERSISTED_FIELDS:
            if field in data:
                if field == "mcp_connectors":
                    setattr(self, field, [MCPConnectorDef.model_validate(item) for item in data[field]])
                else:
                    setattr(self, field, data[field])
        _key_env_map = {
            "default_llm_api_key": "GEMINI_API_KEY",
            "tinker_api_key": "TINKER_API_KEY",
            "wandb_api_key": "WANDB_API_KEY",
            "hf_token": "HF_TOKEN",
        }
        for field, env_var in _key_env_map.items():
            val = getattr(self, field)
            if val and not os.environ.get(env_var):
                os.environ[env_var] = val

    def save(self) -> None:
        """Persist user-settable fields to the config file.

        Does a read-modify-write to preserve Electron-owned fields
        (connectors, user info, auth credentials, etc.).
        """
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if CONFIG_PATH.exists():
            try:
                existing = json.loads(CONFIG_PATH.read_text())
            except Exception:
                pass
        for f in _PERSISTED_FIELDS:
            val = getattr(self, f)
            existing[f] = [item.model_dump() for item in val] if f == "mcp_connectors" else val
        CONFIG_PATH.write_text(json.dumps(existing, indent=2))
