"""Server configuration — mirrors run_online.py args as a Pydantic model."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_PATH = Path(os.environ.get("TADA_CONFIG_PATH", "tada-config.json"))
CONFIG_DEFAULTS_PATH = Path(
    os.environ.get(
        "TADA_CONFIG_DEFAULTS_PATH",
        str(CONFIG_PATH.with_name("tada-config.defaults.json")),
    )
)

# Default model identifiers — single source of truth for Python.
DEFAULT_LLM_MODEL = "gemini/gemini-3.1-flash-lite-preview"
DEFAULT_TINKER_MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"
DEFAULT_AGENT_MODEL = "anthropic/claude-sonnet-4-6"

# Fields exposed via GET/PUT /api/settings (the UI settings panel).
SETTINGS_API_FIELDS: frozenset[str] = frozenset({
    "default_llm_api_key", "tinker_api_key", "hf_token", "wandb_api_key",
    "model", "reward_llm", "reward_llm_api_key",
    "label_model", "label_model_api_key",
    "filter_model", "filter_model_api_key",
    "fps", "num_generations",
    "learning_rate", "batch_size", "past_len", "future_len", "loss_mode",
    "memory_enabled", "memory_agent_model", "memory_agent_api_key",
    "moments_enabled", "moments_agent_model", "moments_agent_api_key",
    "seeker_enabled", "seeker_model", "seeker_api_key",
    "tabracadabra_enabled", "tabracadabra_model", "tabracadabra_api_key",
    "agent_model", "agent_api_key",
    "feature_flags",
    # Persisted directly via PUT /api/settings during onboarding (and by the
    # connector toggle UI later). The settings UI does not surface this field —
    # it's allowlisted there explicitly — so exposing it here just gives the
    # onboarding flow a single, idempotent write path.
    "enabled_connectors",
})

# All fields that are user-settable and persisted to disk.
# Superset of SETTINGS_API_FIELDS — includes internal fields not shown in the UI.
_PERSISTED_FIELDS = SETTINGS_API_FIELDS | {
    "model_type",
    "connector_errors", "mcp_connectors",
    "onboarding_complete", "onboarding_steps_seen",
    "memory_enabled", "memory_agent_model", "memory_agent_api_key", "memory_schedule",
    "tada_dir", "moments_agent_model", "moments_agent_api_key", "moments_discovery_schedule", "moments_enabled",
    "moments_executor_concurrency",
    "seeker_enabled", "seeker_model", "seeker_api_key",
    "tabracadabra_enabled", "tabracadabra_model", "tabracadabra_api_key",
    "agent_model", "agent_api_key",
    "feature_flags",
}


class MCPConnectorDef(BaseModel):
    """Definition of a community or custom MCP server to use as a Tada connector."""

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
    # API keys (populated via settings endpoint or persisted config)
    default_llm_api_key: str = ""
    tinker_api_key: str = ""
    hf_token: str = ""
    wandb_api_key: str = ""

    # Recorder
    fps: int = 5
    buffer_seconds: int = 120
    precision: str = "accurate"

    # Labeler
    label_model: str = DEFAULT_LLM_MODEL
    label_model_api_key: str = ""
    filter_model: str = DEFAULT_LLM_MODEL
    filter_model_api_key: str = ""
    chunk_workers: int = 4

    # Model selection
    model_type: str = "prompted"

    @property
    def prompted_model(self) -> str:
        return self.tabracadabra_model

    # Trainer
    model: str = DEFAULT_TINKER_MODEL
    reward_llm: str = DEFAULT_LLM_MODEL
    reward_llm_api_key: str = ""
    num_generations: int = 4
    learning_rate: float = 5e-5
    max_completion_length: int = 512
    num_imgs_per_sample: int | None = 5
    loss_mode: str = "llm_judge"
    eval_with_llm_judge: bool = False
    batch_size: int = 8
    past_len: int = 50
    future_len: int = 8

    # Inference
    predict_every_n_seconds: int = 10

    # Tabracadabra
    tabracadabra_enabled: bool = True
    tabracadabra_model: str = DEFAULT_LLM_MODEL
    tabracadabra_api_key: str = ""

    # Agent
    agent_model: str = DEFAULT_AGENT_MODEL
    agent_api_key: str = ""

    # Logging
    log_dir: str = Field(default_factory=lambda: os.getenv("TADA_LOG_DIR", "./logs"))
    log_to_wandb: bool = Field(default_factory=lambda: os.getenv("TADA_LOG_TO_WANDB", "") == "1")
    wandb_project: str = Field(default_factory=lambda: os.getenv("TADA_WANDB_PROJECT", "longnap-online"))
    wandb_run_name: str = Field(default_factory=lambda: os.getenv("TADA_WANDB_RUN_NAME", "longnap-online-env"))

    # Google token path (for Gmail / Calendar connectors)
    google_token_path: str = Field(default_factory=lambda: os.getenv("TADA_GOOGLE_TOKEN_PATH", ""))

    # Outlook token path (for Outlook Email / Calendar connectors)
    outlook_token_path: str = Field(default_factory=lambda: os.getenv("TADA_OUTLOOK_TOKEN_PATH", ""))

    # Recording persistence
    save_recordings: bool = Field(default_factory=lambda: os.getenv("TADA_SAVE_RECORDINGS", "") == "1")

    # Checkpointing
    checkpoint_every_n_steps: int = 2
    resume_from_checkpoint: str | None = Field(default_factory=lambda: os.getenv("TADA_RESUME_FROM_CHECKPOINT") or None)
    retriever_checkpoint: str | None = Field(default_factory=lambda: os.getenv("TADA_RETRIEVER_CHECKPOINT") or None)
    sampler_ttl_seconds: int = 60

    # Memory wiki
    memory_enabled: bool = True
    memory_agent_model: str = Field(default_factory=lambda: os.getenv("TADA_AGENT_MODEL", DEFAULT_AGENT_MODEL))
    memory_agent_api_key: str = ""
    memory_schedule: str = "daily at 3am"

    # Seeker
    seeker_enabled: bool = True
    seeker_model: str = Field(default_factory=lambda: os.getenv("TADA_AGENT_MODEL", DEFAULT_AGENT_MODEL))
    seeker_api_key: str = ""

    # Moments
    tada_dir: str = Field(default_factory=lambda: os.getenv(
        "TADA_TADA_DIR",
        str(Path(os.getenv("TADA_LOG_DIR", "./logs")).resolve().parent / "logs-tada"),
    ))
    moments_agent_model: str = Field(default_factory=lambda: os.getenv("TADA_AGENT_MODEL", DEFAULT_AGENT_MODEL))
    moments_discovery_schedule: str = "daily at 2am"
    moments_agent_api_key: str = ""
    moments_enabled: bool = True
    # Max number of tada executions running concurrently. Higher values reduce
    # wall-clock latency for due tadas but multiply LLM spend and can hit
    # provider rate limits — tune downward if you see 429s or cost spikes.
    moments_executor_concurrency: int = 5

    # Connectors: names of connectors that are enabled (running)
    enabled_connectors: list[str] = Field(default_factory=list)

    # Connector error messages persisted across restarts (name → error string)
    connector_errors: dict[str, str] = Field(default_factory=dict)

    # Community / custom MCP connectors added by the user
    mcp_connectors: list[MCPConnectorDef] = Field(default_factory=list)

    # Onboarding completion flag (set by POST /api/onboarding/finalize)
    onboarding_complete: bool = False

    # Step IDs the user has finished in any onboarding run. Used to detect
    # when a newer app version has added steps the user has not yet seen,
    # so we can open onboarding directly on just those steps.
    onboarding_steps_seen: list[str] = Field(default_factory=list)

    # Feature flags (deployment-level gates for entire features/connectors/permissions)
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    def resolve_api_key(self, key: str) -> str | None:
        """Return the feature-specific API key, falling back to default_llm_api_key."""
        return getattr(self, key, None) or self.default_llm_api_key or None

    def load_persisted(self) -> None:
        """Load user-settable fields from defaults + config file, if they exist.

        CLI-arg-derived fields (log_dir, token paths, etc.) are not overwritten.
        """
        for cfg_path in (CONFIG_DEFAULTS_PATH, CONFIG_PATH):
            if not cfg_path.exists():
                continue
            try:
                data = json.loads(cfg_path.read_text())
            except Exception:
                continue
            for field in _PERSISTED_FIELDS:
                if field in data:
                    if field == "mcp_connectors":
                        setattr(self, field, [MCPConnectorDef.model_validate(item) for item in data[field]])
                    elif field == "feature_flags":
                        existing = getattr(self, field, {}) or {}
                        setattr(self, field, {**existing, **data[field]})
                    else:
                        setattr(self, field, data[field])

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
