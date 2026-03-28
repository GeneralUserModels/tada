"""Scheduler: scans logs-tada/ for due tasks and runs the executor."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time as _time
from datetime import datetime, time, timedelta
from pathlib import Path

from server.services.moments_executor import execute_moment, parse_frontmatter
from server.ws.handler import broadcast

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 60  # seconds between schedule checks

_DOW = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6}


def _parse_time(s: str) -> time | None:
    """Parse time strings like '8am', '5pm', '9:30am'."""
    s = s.strip().lower()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if m.group(3) == "pm" and hour != 12:
        hour += 12
    elif m.group(3) == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def _next_run_time(schedule: str, frequency: str) -> datetime | None:
    """Compute the next run datetime from a human-readable schedule string."""
    schedule_lower = schedule.lower().strip()
    now = datetime.now()

    if frequency == "daily":
        time_match = re.search(r"(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", schedule_lower)
        if not time_match:
            return None
        t = _parse_time(time_match.group(1))
        if not t:
            return None
        candidate = datetime.combine(now.date(), t)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "weekly":
        day_name = None
        for name in _DOW:
            if name in schedule_lower:
                day_name = name
                break
        time_match = re.search(r"(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", schedule_lower)
        if not time_match:
            return None
        t = _parse_time(time_match.group(1))
        if not t:
            return None
        target_dow = _DOW[day_name] if day_name else now.weekday()
        days_ahead = (target_dow - now.weekday()) % 7
        candidate = datetime.combine(now.date() + timedelta(days=days_ahead), t)
        if candidate <= now:
            candidate += timedelta(weeks=1)
        return candidate

    return None


def load_run_history(results_dir: Path) -> dict[str, float]:
    """Load last successful run timestamp per slug from _runs.jsonl."""
    runs_file = results_dir / "_runs.jsonl"
    history: dict[str, float] = {}
    if not runs_file.exists():
        return history
    for line in runs_file.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("status") == "success":
            history[entry["slug"]] = entry["completed_at"]
    return history


def save_run(results_dir: Path, slug: str, started_at: float, completed_at: float, status: str):
    """Append a run record to _runs.jsonl."""
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / "_runs.jsonl", "a") as f:
        json.dump({"slug": slug, "started_at": started_at, "completed_at": completed_at, "status": status}, f)
        f.write("\n")


def should_run(slug: str, frequency: str, schedule: str, run_history: dict[str, float]) -> bool:
    """Determine if a task should run now based on its schedule and run history."""
    last_run = run_history.get(slug)
    now = datetime.now()

    if frequency == "once":
        return last_run is None

    next_run = _next_run_time(schedule, frequency)
    if next_run is None:
        return False

    if last_run is None:
        if frequency == "daily":
            return next_run.date() == now.date() or next_run <= now + timedelta(minutes=2)
        return True

    last_dt = datetime.fromtimestamp(last_run)
    if frequency == "daily":
        return last_dt.date() < now.date() and next_run <= now + timedelta(minutes=2)
    if frequency == "weekly":
        return (now - last_dt) >= timedelta(days=6) and next_run <= now + timedelta(minutes=2)
    return False


async def run_moments_scheduler(state) -> None:
    """Background task: scan logs-tada/ and execute due moments."""
    logger.info("Moments scheduler started")
    executor_lock = state.moments_executor_lock
    model = state.config.moments_agent_model
    logs_dir = str(Path(state.config.log_dir).resolve())

    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL)

            tada_dir = Path(state.config.tada_dir).resolve()
            if not tada_dir.exists():
                continue

            results_dir = tada_dir / "results"
            results_dir.mkdir(parents=True, exist_ok=True)
            run_history = load_run_history(results_dir)

            for md_file in sorted(tada_dir.glob("*.md")):
                fm = parse_frontmatter(md_file.read_text())
                frequency = fm.get("frequency", "")
                schedule = fm.get("schedule", "")
                if frequency not in ("daily", "weekly", "once"):
                    continue

                slug = md_file.stem
                if not should_run(slug, frequency, schedule, run_history):
                    continue
                if executor_lock.locked():
                    logger.debug(f"Executor busy, skipping {slug} this cycle")
                    continue

                async with executor_lock:
                    started_at = _time.time()
                    output_dir = str(results_dir / slug)
                    logger.info(f"Executing moment: {slug}")
                    success = await asyncio.to_thread(execute_moment, str(md_file), output_dir, logs_dir, model)
                    completed_at = _time.time()
                    save_run(results_dir, slug, started_at, completed_at, "success" if success else "failed")
                    run_history[slug] = completed_at

                    if success:
                        meta_path = Path(output_dir) / "meta.json"
                        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                        await broadcast(state, "moment_completed", {
                            "slug": slug,
                            "title": meta.get("title", fm.get("title", slug)),
                            "description": meta.get("description", fm.get("description", "")),
                            "completed_at": meta.get("completed_at", datetime.now().isoformat()),
                            "frequency": frequency,
                            "schedule": schedule,
                        })
                        logger.info(f"Moment completed: {slug}")
                    else:
                        logger.warning(f"Moment failed: {slug}")

        except asyncio.CancelledError:
            logger.info("Moments scheduler stopped")
            return
        except Exception:
            logger.exception("Moments scheduler error")
            await asyncio.sleep(60)
