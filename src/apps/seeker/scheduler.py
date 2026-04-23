"""Scheduler: runs seek.py once every 24h. seek.py decides what to do with any existing questions."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from server.feature_flags import is_enabled

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 60  # seconds between checks


def _conversations_dir(state) -> Path:
    return Path(state.config.log_dir).resolve() / "active-conversations"


def _state_path(state) -> Path:
    return _conversations_dir(state) / "seeker_state.json"


def _load_seeker_state(state) -> dict:
    path = _state_path(state)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_seeker_state(state, data: dict):
    path = _state_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _should_run(state) -> bool:
    """Check if seek.py should run: enabled, not mid-conversation, 24h cooldown."""
    if not (is_enabled(state.config, "seeker") and state.config.seeker_enabled):
        return False

    if state.seeker_session is not None:
        return False

    seeker_state = _load_seeker_state(state)
    last_run = seeker_state.get("last_seek_run")
    if last_run:
        last_dt = datetime.fromisoformat(last_run)
        if datetime.now() - last_dt < timedelta(hours=24):
            return False

    return True


async def run_seeker_scheduler(state) -> None:
    """Background task: run seek.py once every 24h; seek.py curates any pre-existing questions."""
    logger.info("Seeker scheduler started")

    from agent.builder import _ensure_sandbox_async
    logs_dir = str(Path(state.config.log_dir).resolve())
    await _ensure_sandbox_async([logs_dir])

    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL)

            if not _should_run(state):
                continue

            logger.info("Seeker scheduler: running seek.py")
            cfg = state.config
            log_dir = str(Path(cfg.log_dir).resolve())
            model = cfg.seeker_model
            api_key = cfg.seeker_api_key or cfg.moments_agent_api_key or cfg.resolve_api_key("agent_api_key")

            # Record timestamp before running so failures don't cause retries within the same day
            seeker_state = _load_seeker_state(state)
            seeker_state["last_seek_run"] = datetime.now().isoformat()
            _save_seeker_state(state, seeker_state)

            try:
                seek_msg = "Generating questions…"
                await state.broadcast_activity("seeker", seek_msg)
                on_round = state.make_round_callback("seeker", seek_msg)
                await asyncio.to_thread(_run_seek, log_dir, model, api_key, on_round=on_round)
            finally:
                await state.broadcast_activity("seeker")

            logger.info("Seeker scheduler: seek.py completed, broadcasting")
            await state.broadcast("seeker_questions_ready", {})

        except asyncio.CancelledError:
            logger.info("Seeker scheduler stopped")
            return
        except Exception:
            logger.exception("Seeker scheduler error")
            await asyncio.sleep(300)


def _run_seek(logs_dir: str, model: str, api_key: str | None, on_round=None):
    """Wrapper to import and run seek in a thread."""
    from apps.seeker.seek import run as seek_run
    return seek_run(logs_dir, model, api_key=api_key, on_round=on_round)
