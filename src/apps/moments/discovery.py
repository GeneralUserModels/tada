"""Discovery service: periodically finds new moments from activity logs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


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


def _read_last_run(p: Path) -> datetime | None:
    """Read the last discovery run timestamp from disk."""
    if not p.exists():
        return None
    try:
        return datetime.fromisoformat(p.read_text().strip())
    except (ValueError, OSError):
        return None


async def run_moments_discovery(state) -> None:
    """Background task: run the full discovery pipeline at a fixed daily time.

    If the scheduled time has already passed today but we haven't run yet
    (e.g. the computer was off at 2am), run immediately on wake.
    """
    from apps.moments.scheduler import _next_run_time, _parse_time

    logger.info("Moments discovery service started")

    while True:
        try:
            schedule = getattr(state.config, "moments_discovery_schedule", "daily at 2am")
            next_run = _next_run_time(schedule, "daily")
            if next_run is None:
                logger.warning("Cannot parse discovery schedule %r, retrying in 1h", schedule)
                await asyncio.sleep(3600)
                continue

            # Check if we missed today's run (e.g. computer was off at scheduled time)
            now = datetime.now()
            scheduled_time = _parse_time(schedule)
            today_target = datetime.combine(now.date(), scheduled_time) if scheduled_time else None
            last_run_file = Path(state.config.log_dir).resolve() / ".discovery_last_run"
            last_run = _read_last_run(last_run_file)
            missed = (
                today_target is not None
                and now > today_target
                and (last_run is None or last_run < today_target)
            )

            if missed:
                logger.info("Missed scheduled discovery at %s, running now", today_target)
            else:
                delay = (next_run - now).total_seconds()
                logger.info("Next discovery run at %s (in %.0fs)", next_run, delay)
                await asyncio.sleep(delay)

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

            last_run_file.write_text(datetime.now().isoformat())
            logger.info("Discovery pipeline complete")

        except asyncio.CancelledError:
            logger.info("Moments discovery service stopped")
            return
        except Exception:
            logger.exception("Moments discovery error")
            await asyncio.sleep(300)


def main():
    """Run the full discovery pipeline once: discover moments, oneoffs, then filter."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run moments discovery pipeline")
    parser.add_argument("--logs-dir", default=os.getenv("POWERNAP_LOG_DIR", "./logs"),
                        help="Path to logs directory (default: $POWERNAP_LOG_DIR or ./logs)")
    parser.add_argument("--model", default=os.getenv("POWERNAP_AGENT_MODEL", "anthropic/claude-sonnet-4-20250514"),
                        help="Model to use for discovery")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY", ""),
                        help="API key (default: $ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    logs_dir = str(Path(args.logs_dir).resolve())
    api_key = args.api_key or None

    logger.info("Discovery: finding recurring moments in %s", logs_dir)
    MomentsDiscovery(logs_dir, args.model, api_key).run()

    logger.info("Discovery: finding one-off moments")
    OneoffsDiscovery(logs_dir, args.model, api_key).run()

    logger.info("Discovery: filtering tasks")
    TaskFilter(logs_dir, args.model, api_key).run()

    logger.info("Discovery pipeline complete")


if __name__ == "__main__":
    main()
