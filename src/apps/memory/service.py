"""Memory wiki service: periodically ingests logs and lints the wiki."""

from __future__ import annotations

import argparse
import os
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from server.feature_flags import is_enabled
from agent.builder import _ensure_sandbox_async
from apps.moments.runtime.scheduler import is_due
from server.cost_tracker import init_cost_tracking
from server.config import DEFAULT_AGENT_MODEL

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 60  # seconds between schedule checks

class MemoryIngest:
    """Ingests new activity logs into the personal knowledge wiki."""

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

    def run(self, on_round=None) -> str:
        """Read new logs and update wiki pages. Blocking."""
        from apps.memory.ingest import run as ingest_run
        return ingest_run(
            self.logs_dir, model=self.model, api_key=self.api_key, on_round=on_round,
            subagent_model=self.subagent_model, subagent_api_key=self.subagent_api_key,
        )


class MemoryLint:
    """Audits and maintains wiki health."""

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

    def run(self, on_round=None) -> str:
        """Lint the wiki. Blocking."""
        from apps.memory.lint import run as lint_run
        return lint_run(
            self.logs_dir, model=self.model, api_key=self.api_key, on_round=on_round,
            subagent_model=self.subagent_model, subagent_api_key=self.subagent_api_key,
        )


def _read_last_run(p: Path) -> datetime | None:
    """Read a last-run timestamp from disk."""
    if not p.exists():
        return None
    try:
        return datetime.fromisoformat(p.read_text().strip())
    except (ValueError, OSError):
        return None


def _memory_ingest_due(schedule: str, last_run: datetime | None) -> bool:
    """Return whether the scheduled Memex ingest should run now."""
    return is_due(schedule, "scheduled", last_run)


async def run_memory_service(state) -> None:
    """Background task: poll every SCAN_INTERVAL and run ingest whenever the
    most recent scheduled occurrence hasn't completed yet. Lint runs alongside
    ingest if its own 6-day cooldown has elapsed.
    """

    logger.info("Memory wiki service started")

    logs_dir = str(Path(state.config.log_dir).resolve())
    last_run_file = Path(logs_dir) / "memory" / ".memory_last_run"
    lint_last_run_file = Path(logs_dir) / "memory" / ".memory_lint_last_run"

    # Pre-initialize sandbox on the event-loop thread (signal handlers
    # can only be registered here, not inside the worker thread).
    await _ensure_sandbox_async([logs_dir])

    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL)

            if not (is_enabled(state.config, "memory") and state.config.memory_enabled):
                continue

            schedule = getattr(state.config, "memory_schedule", "daily at 3am")
            if not _memory_ingest_due(schedule, _read_last_run(last_run_file)):
                continue

            cfg = state.config
            model = cfg.memory_agent_model
            api_key = cfg.memory_agent_api_key or cfg.resolve_api_key("agent_api_key")
            subagent_model = cfg.subagent_model or None
            subagent_api_key = cfg.resolve_api_key("subagent_api_key") if cfg.subagent_model else None

            try:
                ingest_msg = "Ingesting memories…"
                await state.broadcast_activity("memory", ingest_msg)
                on_round = state.make_round_callback("memory", ingest_msg)
                logger.info("Memory: running ingest")
                await asyncio.to_thread(
                    MemoryIngest(logs_dir, model, api_key, subagent_model, subagent_api_key).run,
                    on_round=on_round,
                )
                logger.info("Memory: ingest complete")
                await state.broadcast("memory_updated", {})

                lint_last_run = _read_last_run(lint_last_run_file)
                should_lint = lint_last_run is None or (datetime.now() - lint_last_run) >= timedelta(days=6)
                if should_lint:
                    lint_msg = "Auditing memories…"
                    await state.broadcast_activity("memory", lint_msg)
                    lint_on_round = state.make_round_callback("memory", lint_msg)
                    logger.info("Memory: running lint (weekly)")
                    await asyncio.to_thread(
                        MemoryLint(logs_dir, model, api_key, subagent_model, subagent_api_key).run,
                        on_round=lint_on_round,
                    )
                    lint_last_run_file.parent.mkdir(parents=True, exist_ok=True)
                    lint_last_run_file.write_text(datetime.now().isoformat())
                    logger.info("Memory: lint complete")

                last_run_file.parent.mkdir(parents=True, exist_ok=True)
                last_run_file.write_text(datetime.now().isoformat())
            finally:
                await state.broadcast_activity("memory")

        except asyncio.CancelledError:
            logger.info("Memory wiki service stopped")
            return
        except Exception:
            logger.exception("Memory wiki service error")
            await asyncio.sleep(300)


def main():
    """Run ingest (and optionally lint) once from the command line."""

    parser = argparse.ArgumentParser(description="Run memory wiki pipeline")
    parser.add_argument("--logs-dir", default=os.getenv("TADA_LOG_DIR", "./logs"),
                        help="Path to logs directory (default: $TADA_LOG_DIR or ./logs)")
    parser.add_argument("--model", default=os.getenv("TADA_AGENT_MODEL", DEFAULT_AGENT_MODEL),
                        help="Model to use")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY", ""),
                        help="API key (default: $ANTHROPIC_API_KEY)")
    parser.add_argument("--lint", action="store_true", help="Also run lint after ingest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

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
