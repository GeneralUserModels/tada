"""Scheduler: scans logs-tada/ for due tasks and runs the executor."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time as _time
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from apps.moments.execute import run as execute_moment, _parse_frontmatter as parse_frontmatter
from apps.moments.paths import list_task_files
from apps.moments.state import clear_pending_update, load_state
from server.feature_flags import is_enabled

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


_FREQUENCY_PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}


def is_due(schedule: str, frequency: str, last_run: datetime | None) -> bool:
    """True if the most recent scheduled occurrence hasn't been completed yet.

    Used by pollers that wake every ~minute and need to catch up after the app
    was closed or the machine was asleep at the scheduled time.
    """
    next_run = _next_run_time(schedule, frequency)
    period = _FREQUENCY_PERIOD.get(frequency)
    if next_run is None or period is None:
        return False
    most_recent_target = next_run - period
    if last_run is None:
        return True
    return last_run < most_recent_target


def should_run(slug: str, frequency: str, schedule: str, run_history: dict[str, float]) -> bool:
    """Determine if a task should run now based on its schedule and run history."""
    last_run = run_history.get(slug)
    now = datetime.now()

    if frequency == "once":
        return last_run is None

    period = _FREQUENCY_PERIOD.get(frequency)
    if period is None:
        return False

    next_run = _next_run_time(schedule, frequency)
    if next_run is None:
        return False

    if last_run is None:
        return True

    # If next_run is more than 2 min away, the scheduled time for this
    # period has already passed — the moment is overdue.
    due_time = next_run if next_run <= now + timedelta(minutes=2) else next_run - period

    # Already executed since the most recent scheduled time — skip.
    last_dt = datetime.fromtimestamp(last_run)
    if last_dt >= due_time:
        return False

    return now >= due_time


async def _execute_one_moment(
    state,
    md_file: Path,
    slug: str,
    fm: dict,
    slug_state: dict,
    effective_frequency: str,
    effective_schedule: str,
    logs_dir: str,
    results_dir: Path,
    tada_dir: Path,
    model: str,
    api_key: str | None,
    last_run_at: float | None,
) -> None:
    """Run a single tada inside the executor semaphore.

    Each instance contends for a slot in `state.moments_executor_sem`; up to
    `config.moments_executor_concurrency` of these run concurrently. Activity
    broadcasts are slug-keyed so multiple concurrent runs don't clobber one
    another's banner.
    """
    output_dir = str(results_dir / slug)
    freq_override = slug_state.get("frequency_override") or None
    sched_override = slug_state.get("schedule_override") or None
    moment_title = fm.get("title", slug)
    run_msg = f"Running: {moment_title}"
    activity_key = f"moment_run:{slug}"
    sem = state.moments_executor_sem

    async with sem:
        started_at = _time.time()
        logger.info(f"Executing moment: {slug}")
        await state.broadcast_activity(
            activity_key, run_msg, slug=slug, frequency=effective_frequency,
        )
        on_round = state.make_round_callback(
            activity_key, run_msg, slug=slug, frequency=effective_frequency,
        )
        try:
            success = await asyncio.to_thread(
                execute_moment, str(md_file), output_dir, logs_dir, model,
                frequency_override=freq_override, schedule_override=sched_override,
                api_key=api_key,
                last_run_at=last_run_at,
                on_round=on_round,
            )
        finally:
            await state.broadcast_activity(activity_key)
        completed_at = _time.time()

        async with state.moments_runs_lock:
            save_run(results_dir, slug, started_at, completed_at, "success" if success else "failed")

        if success:
            clear_pending_update(tada_dir, slug)
            meta_path = Path(output_dir) / "meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            result_dir = Path(output_dir)
            output_files = [
                f for f in result_dir.iterdir()
                if f.is_file() and not f.name.startswith("feedback_")
            ] if result_dir.exists() else []
            true_updated = (
                datetime.fromtimestamp(max(f.stat().st_mtime for f in output_files), tz=timezone.utc).isoformat()
                if output_files else datetime.now().isoformat()
            )
            await state.broadcast("moment_completed", {
                "slug": slug,
                "title": meta.get("title", fm.get("title", slug)),
                "description": meta.get("description", fm.get("description", "")),
                "completed_at": true_updated,
                "frequency": effective_frequency,
                "schedule": effective_schedule,
            })
            logger.info(f"Moment completed: {slug}")
        else:
            logger.warning(f"Moment failed: {slug}")


async def run_moments_scheduler(state) -> None:
    """Background task: scan logs-tada/ and execute due moments concurrently.

    Up to `config.moments_executor_concurrency` tadas execute in parallel
    (via `state.moments_executor_sem`); per-slug deduplication via
    `state.moments_in_flight_slugs` prevents the same slug from being
    dispatched twice while a prior task is still queued/running.
    """
    logger.info("Moments scheduler started")

    # Initialize sandbox in the event loop (signal handlers require main thread)
    from agent.builder import _ensure_sandbox_async
    logs_dir = str(Path(state.config.log_dir).resolve())
    tada_dir = str(Path(state.config.tada_dir).resolve())
    await _ensure_sandbox_async([logs_dir, tada_dir])

    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL)

            if not (is_enabled(state.config, "moments") and state.config.moments_enabled):
                continue

            cfg = state.config
            model = cfg.moments_agent_model
            api_key = cfg.resolve_api_key("moments_agent_api_key")

            tada_dir = Path(state.config.tada_dir).resolve()
            if not tada_dir.exists():
                continue

            results_dir = tada_dir / "results"
            results_dir.mkdir(parents=True, exist_ok=True)
            run_history = load_run_history(results_dir)
            moment_state = load_state(tada_dir)

            for md_file in list_task_files(tada_dir):
                fm = parse_frontmatter(md_file.read_text())
                frequency = fm.get("frequency", "")
                schedule = fm.get("schedule", "")
                if frequency not in ("daily", "weekly", "once"):
                    continue

                slug = md_file.stem
                if slug in state.moments_in_flight_slugs:
                    continue
                slug_state = moment_state.get(slug, {})
                if slug_state.get("dismissed"):
                    continue
                effective_frequency = slug_state.get("frequency_override") or frequency
                effective_schedule = slug_state.get("schedule_override") or schedule
                pending = bool(slug_state.get("pending_update"))
                if not pending and not should_run(slug, effective_frequency, effective_schedule, run_history):
                    continue

                state.moments_in_flight_slugs.add(slug)
                task = asyncio.create_task(_execute_one_moment(
                    state, md_file, slug, fm, slug_state,
                    effective_frequency, effective_schedule,
                    logs_dir, results_dir, tada_dir, model, api_key,
                    run_history.get(slug),
                ))
                state.moments_execution_tasks.add(task)

                def _cleanup(t: asyncio.Task, s: str = slug) -> None:
                    state.moments_in_flight_slugs.discard(s)
                    state.moments_execution_tasks.discard(t)
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc is not None:
                        logger.exception("Moment execution task crashed", exc_info=exc)

                task.add_done_callback(_cleanup)

        except asyncio.CancelledError:
            logger.info("Moments scheduler stopped")
            in_flight = list(state.moments_execution_tasks)
            for t in in_flight:
                t.cancel()
            if in_flight:
                await asyncio.gather(*in_flight, return_exceptions=True)
            return
        except Exception:
            logger.exception("Moments scheduler error")
            await asyncio.sleep(60)
