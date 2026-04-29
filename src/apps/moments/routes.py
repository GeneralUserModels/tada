"""REST endpoints for moments (Tada tab)."""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import asyncio
import time as _time

from apps.moments.execute import _parse_frontmatter as parse_frontmatter
from apps.moments.execute import run as execute_moment
from apps.moments.paths import find_task_md, get_topic, list_task_files
from apps.moments.scheduler import save_run, load_run_history
from apps.moments.state import (
    load_state,
    save_state,
    DEFAULT_SLUG_STATE,
)
from chat import ChatAgent, ChatSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/moments", tags=["moments"])


class MomentStateUpdate(BaseModel):
    dismissed: Optional[bool] = None
    pinned: Optional[bool] = None
    thumbs: Optional[str] = None


class ScheduleUpdate(BaseModel):
    frequency: str
    schedule: str


class ViewEnd(BaseModel):
    duration_ms: int


def _get_tada_dir(request: Request) -> Path:
    return Path(request.app.state.server.config.tada_dir).resolve()


@router.get("/tasks")
async def list_tasks(request: Request):
    """List all scheduled tasks from logs-tada/<topic>/*.md (daily/weekly/once only)."""
    tada_dir = _get_tada_dir(request)
    if not tada_dir.exists():
        return []
    tasks = []
    for md_file in list_task_files(tada_dir):
        fm = parse_frontmatter(md_file.read_text())
        frequency = fm.get("frequency", "")
        if frequency not in ("daily", "weekly", "once"):
            continue
        tasks.append({
            "slug": md_file.stem,
            "title": fm.get("title", md_file.stem),
            "description": fm.get("description", ""),
            "frequency": frequency,
            "schedule": fm.get("schedule", ""),
            "confidence": float(fm.get("confidence", 0)),
            "usefulness": int(fm.get("usefulness", 0)),
            "topic": get_topic(md_file, tada_dir),
        })
    return tasks


@router.get("/results")
async def list_results(request: Request, include_dismissed: bool = False):
    """List completed moment results, sorted by most recent first."""
    tada_dir = _get_tada_dir(request)
    results_dir = tada_dir / "results"
    if not results_dir.exists():
        return []

    all_state = load_state(tada_dir)
    # Build slug -> topic map once so each result row can carry its topic
    # without re-globbing per slug.
    slug_topics: dict[str, str] = {
        md.stem: get_topic(md, tada_dir) for md in list_task_files(tada_dir)
    }
    results = []
    for meta_path in results_dir.glob("*/meta.json"):
        index_path = meta_path.parent / "index.html"
        if not index_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        slug = meta_path.parent.name
        slug_state = {**DEFAULT_SLUG_STATE, **all_state.get(slug, {})}

        if slug_state["dismissed"] and not include_dismissed:
            continue

        # index.html's shell often stays stable across reruns and meta.json's
        # agent-written completed_at can be hallucinated. Take the freshest
        # mtime across agent-written output files, skipping user-interaction
        # artifacts like feedback_*.md that would inflate "last updated".
        result_dir = meta_path.parent
        output_files = [
            f for f in result_dir.iterdir()
            if f.is_file() and not f.name.startswith("feedback_")
        ]
        mtime = max(f.stat().st_mtime for f in output_files)
        completed_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        # Feedback status
        feedback_files = list(meta_path.parent.glob("feedback_*.md"))
        has_feedback = len(feedback_files) > 0
        feedback_incorporated = False
        last_incorporated = slug_state.get("last_feedback_incorporated_at")
        if has_feedback and last_incorporated:
            latest_feedback_mtime = max(os.path.getmtime(f) for f in feedback_files)
            latest_feedback_dt = datetime.fromtimestamp(latest_feedback_mtime, tz=timezone.utc)
            incorporated_dt = datetime.fromisoformat(last_incorporated)
            feedback_incorporated = latest_feedback_dt < incorporated_dt

        results.append({
            "slug": slug,
            "title": meta.get("title", slug),
            "description": meta.get("description", ""),
            "completed_at": completed_at,
            "frequency": meta.get("frequency", ""),
            "schedule": meta.get("schedule", ""),
            "topic": slug_topics.get(slug, ""),
            "has_feedback": has_feedback,
            "feedback_incorporated": feedback_incorporated,
            **slug_state,
        })

    # Pinned first, then by completed_at descending
    results.sort(key=lambda r: (not r["pinned"], r["completed_at"]), reverse=False)
    results.sort(key=lambda r: r["completed_at"], reverse=True)
    results.sort(key=lambda r: not r["pinned"])
    return results


@router.get("/results/{slug}/index.html")
async def get_result_html(slug: str, request: Request):
    """Serve the agent-generated HTML for a completed moment."""
    path = _get_tada_dir(request) / "results" / slug / "index.html"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="text/html")


@router.get("/results/{slug}/{filename:path}")
async def get_result_asset(slug: str, filename: str, request: Request):
    """Serve additional assets from a result directory."""
    path = _get_tada_dir(request) / "results" / slug / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)


@router.put("/{slug}/state")
async def update_moment_state(slug: str, body: MomentStateUpdate, request: Request):
    """Set dismissed and/or pinned for a moment."""
    tada_dir = _get_tada_dir(request)
    all_state = load_state(tada_dir)
    entry = {**DEFAULT_SLUG_STATE, **all_state.get(slug, {})}

    if body.pinned is not None:
        entry["pinned"] = body.pinned
        if body.pinned:
            entry["dismissed"] = False
    if body.dismissed is not None:
        entry["dismissed"] = body.dismissed
        if body.dismissed:
            entry["pinned"] = False
    if body.thumbs is not None:
        if body.thumbs not in ("up", "down", "clear"):
            return JSONResponse({"error": "thumbs must be 'up', 'down', or 'clear'"}, status_code=400)
        entry["thumbs"] = None if body.thumbs == "clear" else body.thumbs

    all_state[slug] = entry
    save_state(tada_dir, all_state)
    return entry


@router.put("/{slug}/schedule")
async def update_moment_schedule(slug: str, body: ScheduleUpdate, request: Request):
    """Update the schedule/frequency overrides for a moment."""
    if body.frequency not in ("daily", "weekly", "once"):
        return JSONResponse({"error": "frequency must be daily, weekly, or once"}, status_code=400)

    tada_dir = _get_tada_dir(request)
    all_state = load_state(tada_dir)
    entry = {**DEFAULT_SLUG_STATE, **all_state.get(slug, {})}
    entry["frequency_override"] = body.frequency
    entry["schedule_override"] = body.schedule
    all_state[slug] = entry
    save_state(tada_dir, all_state)
    return entry


@router.post("/{slug}/view")
async def record_view(slug: str, request: Request):
    """Record a view event: increments view_count, sets last_viewed."""
    tada_dir = _get_tada_dir(request)
    all_state = load_state(tada_dir)
    entry = {**DEFAULT_SLUG_STATE, **all_state.get(slug, {})}
    entry["view_count"] = entry.get("view_count", 0) + 1
    entry["last_viewed"] = datetime.now(tz=timezone.utc).isoformat()
    all_state[slug] = entry
    save_state(tada_dir, all_state)
    return {"view_count": entry["view_count"]}


@router.post("/{slug}/view-end")
async def record_view_end(slug: str, body: ViewEnd, request: Request):
    """Record view duration."""
    tada_dir = _get_tada_dir(request)
    all_state = load_state(tada_dir)
    entry = {**DEFAULT_SLUG_STATE, **all_state.get(slug, {})}
    entry["time_spent_ms"] = entry.get("time_spent_ms", 0) + body.duration_ms
    all_state[slug] = entry
    save_state(tada_dir, all_state)
    return {"time_spent_ms": entry["time_spent_ms"]}


# ── Re-execution ─────────────────────────────────────────────

@router.post("/{slug}/rerun")
async def rerun_moment(slug: str, request: Request):
    """Trigger an immediate re-execution of a moment."""
    state = request.app.state.server
    tada_dir = _get_tada_dir(request)
    task_path = find_task_md(tada_dir, slug)

    if task_path is None:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    # Reject if this exact slug is already running/queued (via scheduler or
    # a prior rerun) — re-firing the same tada concurrently would race on the
    # shared output dir.
    if slug in state.moments_in_flight_slugs:
        return JSONResponse({"error": "This moment is already executing"}, status_code=409)

    # Reject if the executor pool is fully booked. Non-blocking: we don't
    # want the HTTP request to hang waiting for a slot. The user can retry.
    if state.moments_executor_sem.locked():
        return JSONResponse({"error": "All execution slots are busy"}, status_code=409)

    cfg = state.config
    model = cfg.moments_agent_model
    api_key = cfg.resolve_api_key("moments_agent_api_key")
    logs_dir = str(Path(cfg.log_dir).resolve())
    results_dir = tada_dir / "results"
    output_dir = str(results_dir / slug)

    fm = parse_frontmatter(task_path.read_text())
    all_state = load_state(tada_dir)
    slug_state = all_state.get(slug, {})
    freq_override = slug_state.get("frequency_override") or None
    sched_override = slug_state.get("schedule_override") or None
    run_history = load_run_history(results_dir)

    state.moments_in_flight_slugs.add(slug)

    async def _run_rerun():
        try:
            async with state.moments_executor_sem:
                await state.broadcast("moment_rerun_started", {"slug": slug})
                started_at = _time.time()
                logger.info(f"Re-executing moment: {slug}")

                # Signal handlers require main thread — pre-init before to_thread.
                from agent.builder import _ensure_sandbox_async
                await _ensure_sandbox_async([logs_dir, str(tada_dir.resolve())])

                moment_title = fm.get("title", slug)
                run_msg = f"Running: {moment_title}"
                effective_frequency = freq_override or fm.get("frequency", "")
                activity_key = f"moment_run:{slug}"
                await state.broadcast_activity(
                    activity_key, run_msg, slug=slug, frequency=effective_frequency,
                )
                on_round = state.make_round_callback(
                    activity_key, run_msg, slug=slug, frequency=effective_frequency,
                )
                try:
                    success = await asyncio.to_thread(
                        execute_moment, str(task_path), output_dir, logs_dir, model,
                        frequency_override=freq_override, schedule_override=sched_override,
                        api_key=api_key,
                        last_run_at=run_history.get(slug),
                        on_round=on_round,
                    )
                finally:
                    await state.broadcast_activity(activity_key)
                completed_at = _time.time()
                async with state.moments_runs_lock:
                    save_run(results_dir, slug, started_at, completed_at, "success" if success else "failed")

                if success:
                    effective_schedule = sched_override or fm.get("schedule", "")
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
                    logger.info(f"Moment re-executed: {slug}")
                else:
                    await state.broadcast("moment_rerun_failed", {"slug": slug})
                    logger.warning(f"Moment rerun failed: {slug}")
        finally:
            state.moments_in_flight_slugs.discard(slug)

    asyncio.create_task(_run_rerun())
    return JSONResponse({"status": "started"}, status_code=202)


# ── Feedback ──────────────────────────────────────────────────

FEEDBACK_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "feedback.txt").read_text()


def _read_moment_files(result_dir: Path) -> str:
    """Read all moment output files for the feedback system prompt."""
    parts = []
    for name in ["meta.json", "app.js", "styles.css", "index.html"]:
        path = result_dir / name
        if path.exists():
            content = path.read_text()
            # Truncate very large files
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            parts.append(f"### {name}\n```\n{content}\n```")
    return "\n\n".join(parts)


def _resolve_feedback_api_key(config) -> str | None:
    return config.moments_agent_api_key or config.resolve_api_key("agent_api_key")


@dataclass
class _FeedbackEntry:
    """In-memory feedback session bound to a stable on-disk transcript path."""
    session: object  # ChatSession
    path: Path


def _persist_feedback(entry: _FeedbackEntry) -> None:
    entry.session.save(entry.path, assistant_label="Tada")
    logger.info(f"Feedback saved to {entry.path}")


async def _stream_feedback_response(entry: _FeedbackEntry):
    """Stream LLM tokens as SSE; persist transcript when the turn completes."""
    async for token in entry.session.respond_stream():
        yield f"data: {json.dumps({'token': token})}\n\n"
    # Save after every turn so transcripts survive the user closing the panel.
    _persist_feedback(entry)
    yield f"data: {json.dumps({'done': True})}\n\n"


class FeedbackMessageBody(BaseModel):
    content: str


@router.post("/{slug}/feedback/start")
async def start_feedback(slug: str, body: FeedbackMessageBody, request: Request):
    """Start a feedback conversation for a moment. First message comes from the user."""
    state = request.app.state.server
    tada_dir = _get_tada_dir(request)
    result_dir = tada_dir / "results" / slug

    if not (result_dir / "index.html").exists():
        return JSONResponse({"error": "Moment not found"}, status_code=404)

    # If a session for this slug is already in memory (e.g. the user closed the
    # panel without calling /end), flush it to its transcript before replacing.
    existing = state.feedback_sessions.pop(slug, None)
    if existing is not None:
        _persist_feedback(existing)

    # Build system prompt with moment context
    meta_path = result_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    file_contents = _read_moment_files(result_dir)
    system_prompt = FEEDBACK_SYSTEM_PROMPT.format(
        title=meta.get("title", slug),
        description=meta.get("description", ""),
        file_contents=file_contents,
    )

    agent = ChatAgent(
        model=state.config.moments_agent_model,
        system_prompt=system_prompt,
        api_key=_resolve_feedback_api_key(state.config),
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    entry = _FeedbackEntry(
        session=ChatSession(agent=agent, done_marker=None),
        path=result_dir / f"feedback_{timestamp}.md",
    )
    state.feedback_sessions[slug] = entry

    # User sends the first message
    entry.session.add_user_message(body.content)

    return StreamingResponse(
        _stream_feedback_response(entry),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{slug}/feedback/message")
async def send_feedback_message(slug: str, body: FeedbackMessageBody, request: Request):
    """Send a message in the active feedback conversation."""
    state = request.app.state.server

    entry = state.feedback_sessions.get(slug)
    if entry is None:
        return JSONResponse({"error": "No active feedback conversation for this moment"}, status_code=409)

    if not body.content.strip():
        return JSONResponse({"error": "Message cannot be empty"}, status_code=400)

    entry.session.add_user_message(body.content)

    return StreamingResponse(
        _stream_feedback_response(entry),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{slug}/feedback/end")
async def end_feedback(slug: str, request: Request):
    """End the feedback conversation and save the transcript."""
    state = request.app.state.server

    entry = state.feedback_sessions.pop(slug, None)
    if entry is None:
        return JSONResponse({"error": "No active feedback conversation for this moment"}, status_code=409)

    _persist_feedback(entry)

    return {"status": "ended", "filename": entry.path.name}


@router.get("/{slug}/feedback/conversation")
async def get_feedback_conversation(slug: str, request: Request):
    """Get the current feedback conversation state."""
    state = request.app.state.server

    entry = state.feedback_sessions.get(slug)
    if entry is not None:
        return {"active": True, "messages": entry.session.visible_messages()}

    return {"active": False, "messages": []}
