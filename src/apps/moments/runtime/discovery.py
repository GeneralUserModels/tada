"""Discovery service: periodically finds new moments from activity logs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from server.feature_flags import is_enabled

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 60  # seconds between schedule checks


class _DiscoveryBase:
    def __init__(
        self,
        logs_dir: str,
        model: str,
        api_key: str | None = None,
        subagent_model: str | None = None,
        subagent_api_key: str | None = None,
    ):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key
        self.subagent_model = subagent_model
        self.subagent_api_key = subagent_api_key


class MomentsDiscovery(_DiscoveryBase):
    """Discovers candidate moments from activity logs."""

    def run(self) -> str:
        """Analyze logs and write task files. Blocking."""
        from apps.moments.steps.discover import run as moments_run
        return moments_run(
            self.logs_dir, model=self.model, api_key=self.api_key,
            subagent_model=self.subagent_model, subagent_api_key=self.subagent_api_key,
        )


class TaskFilter(_DiscoveryBase):
    """Promotes discovered candidates into logs-tada/."""

    def run(self) -> str:
        """Promote candidate moments through tada. Blocking."""
        from apps.moments.steps.promote import run as filter_run
        return filter_run(
            self.logs_dir, model=self.model, api_key=self.api_key,
            subagent_model=self.subagent_model, subagent_api_key=self.subagent_api_key,
        )


class TriggersCheck(_DiscoveryBase):
    """Evaluates trigger conditions on existing tada tasks and re-fires matches."""

    def run(self) -> str:
        """Check triggers and mark fired tasks for re-execution. Blocking."""
        from apps.moments.steps.triggers import run as triggers_run
        return triggers_run(
            self.logs_dir, model=self.model, api_key=self.api_key,
            subagent_model=self.subagent_model, subagent_api_key=self.subagent_api_key,
        )


def _read_last_run(p: Path) -> datetime | None:
    """Read the last discovery run timestamp from disk."""
    if not p.exists():
        return None
    try:
        return datetime.fromisoformat(p.read_text().strip())
    except (ValueError, OSError):
        return None


async def run_moments_discovery(state) -> None:
    """Background task: poll every SCAN_INTERVAL and run the discovery pipeline
    whenever the most recent scheduled occurrence hasn't completed yet.

    Polling (instead of one long sleep to the next target) catches up after
    laptop sleep/wake and avoids drift if the schedule is edited at runtime.
    """
    from apps.moments.runtime.scheduler import is_due

    logger.info("Moments discovery service started")

    # Signal handlers require main thread — pre-init before to_thread.
    from agent.builder import _ensure_sandbox_async
    logs_dir = str(Path(state.config.log_dir).resolve())
    tada_dir = str(Path(state.config.tada_dir).resolve())
    await _ensure_sandbox_async([logs_dir, tada_dir])

    last_run_file = Path(state.config.log_dir).resolve() / "moments" / ".discovery_last_run"

    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL)

            if not (is_enabled(state.config, "moments") and state.config.moments_enabled):
                continue

            schedule = getattr(state.config, "moments_discovery_schedule", "daily at 2am")
            if not is_due(schedule, "scheduled", _read_last_run(last_run_file)):
                continue

            cfg = state.config
            model = cfg.moments_agent_model
            api_key = cfg.resolve_api_key("moments_agent_api_key")
            subagent_model = cfg.subagent_model or None
            subagent_api_key = cfg.resolve_api_key("subagent_api_key") if cfg.subagent_model else None

            try:
                logger.info("Discovery: finding candidate moments")
                await state.broadcast_activity("moments_discovery", "Discovering Tadas…")
                try:
                    await asyncio.to_thread(
                        MomentsDiscovery(logs_dir, model, api_key, subagent_model, subagent_api_key).run,
                    )
                except Exception:
                    logger.exception("Discovery failed; skipping promotion and triggers")
                    continue

                logger.info("Discovery: promoting candidates")
                await state.broadcast_activity("moments_discovery", "Promoting Tadas…")
                await asyncio.to_thread(
                    TaskFilter(logs_dir, model, api_key, subagent_model, subagent_api_key).run,
                )

                logger.info("Discovery: evaluating triggers")
                await state.broadcast_activity("moments_discovery", "Checking Triggers…")
                await asyncio.to_thread(
                    TriggersCheck(logs_dir, model, api_key, subagent_model, subagent_api_key).run,
                )

                last_run_file.write_text(datetime.now().isoformat())
                logger.info("Discovery pipeline complete")
            finally:
                await state.broadcast_activity("moments_discovery")

        except asyncio.CancelledError:
            logger.info("Moments discovery service stopped")
            return
        except Exception:
            logger.exception("Moments discovery error")
            await asyncio.sleep(300)
