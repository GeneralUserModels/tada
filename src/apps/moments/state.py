"""Centralized moment state persistence (dismiss, pin, usage tracking, schedule overrides)."""

import json
from pathlib import Path


def get_state_path(tada_dir: Path) -> Path:
    return tada_dir / "results" / "_moment_state.json"


def load_state(tada_dir: Path) -> dict[str, dict]:
    path = get_state_path(tada_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(tada_dir: Path, state: dict[str, dict]) -> None:
    path = get_state_path(tada_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def get_slug_state(tada_dir: Path, slug: str) -> dict:
    return load_state(tada_dir).get(slug, {})


DEFAULT_SLUG_STATE = {
    "dismissed": False,
    "pinned": False,
    "thumbs": None,
    "view_count": 0,
    "time_spent_ms": 0,
    "last_viewed": None,
    "schedule_override": None,
    "frequency_override": None,
}
