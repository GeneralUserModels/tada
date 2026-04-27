"""Discovery service: periodically finds new moments from activity logs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from server.feature_flags import is_enabled

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 60  # seconds between schedule checks


class MomentsDiscovery:
    """Discovers recurring automation tasks from activity logs."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self, on_round=None) -> str:
        """Analyze logs and write task files. Blocking."""
        from apps.moments.discover import run as moments_run
        return moments_run(self.logs_dir, model=self.model, api_key=self.api_key, on_round=on_round)


class OneoffsDiscovery:
    """Discovers one-off situational tasks from activity logs."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self, on_round=None) -> str:
        """Analyze logs and write one-off task files. Blocking."""
        from apps.moments.oneoffs import run as oneoffs_run
        return oneoffs_run(self.logs_dir, model=self.model, api_key=self.api_key, on_round=on_round)


class TaskFilter:
    """Filters discovered tasks and copies completable ones to logs-tada/."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self, on_round=None) -> str:
        """Filter tasks through tada. Blocking."""
        from apps.moments.filter import run as filter_run
        return filter_run(self.logs_dir, model=self.model, api_key=self.api_key, on_round=on_round)


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
    from apps.moments.scheduler import is_due

    logger.info("Moments discovery service started")

    # Signal handlers require main thread — pre-init before to_thread.
    from agent.builder import _ensure_sandbox_async
    logs_dir = str(Path(state.config.log_dir).resolve())
    tada_dir = str(Path(state.config.tada_dir).resolve())
    await _ensure_sandbox_async([logs_dir, tada_dir])

    last_run_file = Path(state.config.log_dir).resolve() / ".discovery_last_run"

    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL)

            if not (is_enabled(state.config, "moments") and state.config.moments_enabled):
                continue

            schedule = getattr(state.config, "moments_discovery_schedule", "daily at 2am")
            if not is_due(schedule, "daily", _read_last_run(last_run_file)):
                continue

            cfg = state.config
            model = cfg.moments_agent_model
            api_key = cfg.resolve_api_key("moments_agent_api_key")

            try:
                discover_msg = "Discovering Tadas…"
                await state.broadcast_activity("moments_discovery", discover_msg)
                discover_cb = state.make_round_callback("moments_discovery", discover_msg)
                logger.info("Discovery: finding recurring + one-off moments in parallel")
                results = await asyncio.gather(
                    asyncio.to_thread(MomentsDiscovery(logs_dir, model, api_key).run, on_round=discover_cb),
                    asyncio.to_thread(OneoffsDiscovery(logs_dir, model, api_key).run, on_round=discover_cb),
                    return_exceptions=True,
                )
                recurring_ok = not isinstance(results[0], Exception)
                oneoffs_ok = not isinstance(results[1], Exception)
                if not recurring_ok:
                    logger.exception("Recurring discovery failed", exc_info=results[0])
                if not oneoffs_ok:
                    logger.exception("One-offs discovery failed", exc_info=results[1])

                if not (recurring_ok or oneoffs_ok):
                    logger.warning("Both discovery stages failed; skipping filter and last_run update")
                    continue

                filter_msg = "Filtering Tadas…"
                await state.broadcast_activity("moments_discovery", filter_msg)
                filter_cb = state.make_round_callback("moments_discovery", filter_msg)
                logger.info("Discovery: filtering tasks")
                await asyncio.to_thread(TaskFilter(logs_dir, model, api_key).run, on_round=filter_cb)

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


def main():
    """Run the full discovery pipeline once: discover moments, oneoffs, then filter."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run moments discovery pipeline")
    parser.add_argument("--logs-dir", default=os.getenv("TADA_LOG_DIR", "./logs"),
                        help="Path to logs directory (default: $TADA_LOG_DIR or ./logs)")
    parser.add_argument("--model", default=os.getenv("TADA_AGENT_MODEL", "anthropic/claude-sonnet-4-20250514"),
                        help="Model to use for discovery")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY", ""),
                        help="API key (default: $ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    logs_dir = str(Path(args.logs_dir).resolve())
    api_key = args.api_key or None

    async def _run_pipeline() -> None:
        logger.info("Discovery: finding recurring + one-off moments in parallel in %s", logs_dir)
        results = await asyncio.gather(
            asyncio.to_thread(MomentsDiscovery(logs_dir, args.model, api_key).run),
            asyncio.to_thread(OneoffsDiscovery(logs_dir, args.model, api_key).run),
            return_exceptions=True,
        )
        recurring_ok = not isinstance(results[0], Exception)
        oneoffs_ok = not isinstance(results[1], Exception)
        if not recurring_ok:
            logger.exception("Recurring discovery failed", exc_info=results[0])
        if not oneoffs_ok:
            logger.exception("One-offs discovery failed", exc_info=results[1])
        if not (recurring_ok or oneoffs_ok):
            logger.warning("Both discovery stages failed; skipping filter")
            return

        logger.info("Discovery: filtering tasks")
        await asyncio.to_thread(TaskFilter(logs_dir, args.model, api_key).run)

        logger.info("Discovery pipeline complete")

    asyncio.run(_run_pipeline())


if __name__ == "__main__":
    main()
