"""Discovery service: periodically finds new moments from activity logs."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 86400  # 24 hours


class MomentsDiscovery:
    """Discovers recurring automation tasks from activity logs."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self) -> str:
        """Analyze logs and write task files. Blocking."""
        from apps.moments.discover import run as moments_run
        return moments_run(self.logs_dir, model=self.model, api_key=self.api_key)


class OneoffsDiscovery:
    """Discovers one-off situational tasks from activity logs."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self) -> str:
        """Analyze logs and write one-off task files. Blocking."""
        from apps.moments.oneoffs import run as oneoffs_run
        return oneoffs_run(self.logs_dir, model=self.model, api_key=self.api_key)


class TaskFilter:
    """Filters discovered tasks and copies completable ones to logs-tada/."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self) -> str:
        """Filter tasks through tada. Blocking."""
        from apps.moments.filter import run as filter_run
        return filter_run(self.logs_dir, model=self.model, api_key=self.api_key)


async def run_moments_discovery(state) -> None:
    """Background task: periodically run the full discovery pipeline."""
    logger.info("Moments discovery service started")

    while True:
        try:
            interval = getattr(state.config, "moments_discovery_interval", DEFAULT_INTERVAL)
            await asyncio.sleep(interval)

            if not state.config.moments_enabled:
                continue

            cfg = state.config
            logs_dir = str(Path(cfg.log_dir).resolve())
            model = cfg.moments_agent_model
            api_key = cfg.resolve_api_key("moments_agent_api_key")

            logger.info("Discovery: finding recurring moments")
            await asyncio.to_thread(MomentsDiscovery(logs_dir, model, api_key).run)

            logger.info("Discovery: finding one-off moments")
            await asyncio.to_thread(OneoffsDiscovery(logs_dir, model, api_key).run)

            logger.info("Discovery: filtering tasks")
            await asyncio.to_thread(TaskFilter(logs_dir, model, api_key).run)

            logger.info("Discovery pipeline complete")

        except asyncio.CancelledError:
            logger.info("Moments discovery service stopped")
            return
        except Exception:
            logger.exception("Moments discovery error")
            await asyncio.sleep(300)
