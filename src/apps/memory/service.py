"""Memory wiki service: periodically ingests logs and lints the wiki."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from server.feature_flags import is_enabled

logger = logging.getLogger(__name__)


class MemoryIngest:
    """Ingests new activity logs into the personal knowledge wiki."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self) -> str:
        """Read new logs and update wiki pages. Blocking."""
        from apps.memory.ingest import run as ingest_run
        return ingest_run(self.logs_dir, model=self.model, api_key=self.api_key)


class MemoryLint:
    """Audits and maintains wiki health."""

    def __init__(self, logs_dir: str, model: str, api_key: str | None = None):
        self.logs_dir = str(Path(logs_dir).resolve())
        self.model = model
        self.api_key = api_key

    def run(self) -> str:
        """Lint the wiki. Blocking."""
        from apps.memory.lint import run as lint_run
        return lint_run(self.logs_dir, model=self.model, api_key=self.api_key)


def _read_last_run(p: Path) -> datetime | None:
    """Read a last-run timestamp from disk."""
    if not p.exists():
        return None
    try:
        return datetime.fromisoformat(p.read_text().strip())
    except (ValueError, OSError):
        return None


async def run_memory_service(state) -> None:
    """Background task: run ingest daily and lint weekly.

    If the scheduled time has already passed today but we haven't run yet
    (e.g. the computer was off at 3am), run immediately on wake.
    """
    from apps.moments.scheduler import _next_run_time, _parse_time

    logger.info("Memory wiki service started")

    while True:
        try:
            schedule = getattr(state.config, "memory_schedule", "daily at 3am")
            next_run = _next_run_time(schedule, "daily")
            if next_run is None:
                logger.warning("Cannot parse memory schedule %r, retrying in 1h", schedule)
                await asyncio.sleep(3600)
                continue

            # Check if we missed today's run
            now = datetime.now()
            time_match = re.search(r"(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", schedule.lower())
            scheduled_time = _parse_time(time_match.group(1)) if time_match else None
            today_target = datetime.combine(now.date(), scheduled_time) if scheduled_time else None
            last_run_file = Path(state.config.log_dir).resolve() / "memory" / ".memory_last_run"
            last_run = _read_last_run(last_run_file)
            missed = (
                today_target is not None
                and now > today_target
                and (last_run is None or last_run < today_target)
            )

            if missed:
                logger.info("Missed scheduled memory ingest at %s, running now", today_target)
            else:
                delay = (next_run - now).total_seconds()
                logger.info("Next memory ingest at %s (in %.0fs)", next_run, delay)
                await asyncio.sleep(delay)

            if not (is_enabled(state.config, "memory") and state.config.memory_enabled):
                continue

            cfg = state.config
            logs_dir = str(Path(cfg.log_dir).resolve())
            model = cfg.memory_agent_model
            api_key = cfg.resolve_api_key("memory_agent_api_key")

            # Always run ingest
            logger.info("Memory: running ingest")
            await asyncio.to_thread(MemoryIngest(logs_dir, model, api_key).run)
            logger.info("Memory: ingest complete")
            await state.broadcast("memory_updated", {})

            # Run lint if last lint was >6 days ago
            lint_last_run_file = Path(logs_dir) / "memory" / ".memory_lint_last_run"
            lint_last_run = _read_last_run(lint_last_run_file)
            should_lint = lint_last_run is None or (now - lint_last_run) >= timedelta(days=6)

            if should_lint:
                logger.info("Memory: running lint (weekly)")
                await asyncio.to_thread(MemoryLint(logs_dir, model, api_key).run)
                lint_last_run_file.parent.mkdir(parents=True, exist_ok=True)
                lint_last_run_file.write_text(datetime.now().isoformat())
                logger.info("Memory: lint complete")

            last_run_file.parent.mkdir(parents=True, exist_ok=True)
            last_run_file.write_text(datetime.now().isoformat())

        except asyncio.CancelledError:
            logger.info("Memory wiki service stopped")
            return
        except Exception:
            logger.exception("Memory wiki service error")
            await asyncio.sleep(300)


def main():
    """Run ingest (and optionally lint) once from the command line."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run memory wiki pipeline")
    parser.add_argument("--logs-dir", default=os.getenv("TADA_LOG_DIR", "./logs"),
                        help="Path to logs directory (default: $TADA_LOG_DIR or ./logs)")
    parser.add_argument("--model", default=os.getenv("TADA_AGENT_MODEL", "anthropic/claude-sonnet-4-20250514"),
                        help="Model to use")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY", ""),
                        help="API key (default: $ANTHROPIC_API_KEY)")
    parser.add_argument("--lint", action="store_true", help="Also run lint after ingest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from server.cost_tracker import init_cost_tracking
    tracker = init_cost_tracking()

    logs_dir = str(Path(args.logs_dir).resolve())
    api_key = args.api_key or None

    logger.info("Memory: running ingest in %s", logs_dir)
    MemoryIngest(logs_dir, args.model, api_key).run()
    logger.info("Memory: ingest complete")

    if args.lint:
        logger.info("Memory: running lint")
        MemoryLint(logs_dir, args.model, api_key).run()
        logger.info("Memory: lint complete")

    snapshot, elapsed = tracker.snapshot()
    total_cost = sum(s["cost"] for s in snapshot.values())
    total_tokens = sum(s["input_tokens"] + s["output_tokens"] for s in snapshot.values())
    logger.info("[cost] memory pipeline — $%.4f total, %d tokens, %.0fs", total_cost, total_tokens, elapsed)


if __name__ == "__main__":
    main()
