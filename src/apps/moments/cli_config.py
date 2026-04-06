import json
from pathlib import Path


def _load_config() -> dict:
    return json.loads(Path("powernap-config.json").read_text())


def resolve_moments_model() -> str:
    return _load_config()["moments_agent_model"]


def resolve_moments_api_key() -> str | None:
    data = _load_config()
    return data.get("moments_agent_api_key") or data.get("default_llm_api_key") or None
