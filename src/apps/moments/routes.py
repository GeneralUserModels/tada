"""REST endpoints for moments (Ta-Da tab)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from apps.moments.execute import _parse_frontmatter as parse_frontmatter
from apps.moments.state import (
    load_state,
    save_state,
    DEFAULT_SLUG_STATE,
)

router = APIRouter(prefix="/api/moments", tags=["moments"])


class MomentStateUpdate(BaseModel):
    dismissed: Optional[bool] = None
    pinned: Optional[bool] = None


class ScheduleUpdate(BaseModel):
    frequency: str
    schedule: str


class ViewEnd(BaseModel):
    duration_ms: int


def _get_tada_dir(request: Request) -> Path:
    return Path(request.app.state.server.config.tada_dir).resolve()


@router.get("/tasks")
async def list_tasks(request: Request):
    """List all scheduled tasks from logs-tada/*.md (daily/weekly/once only)."""
    tada_dir = _get_tada_dir(request)
    if not tada_dir.exists():
        return []
    tasks = []
    for md_file in sorted(tada_dir.glob("*.md")):
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
    results = []
    for meta_path in results_dir.glob("*/meta.json"):
        if not (meta_path.parent / "index.html").exists():
            continue
        meta = json.loads(meta_path.read_text())
        slug = meta_path.parent.name
        slug_state = {**DEFAULT_SLUG_STATE, **all_state.get(slug, {})}

        if slug_state["dismissed"] and not include_dismissed:
            continue

        results.append({
            "slug": slug,
            "title": meta.get("title", slug),
            "description": meta.get("description", ""),
            "completed_at": meta.get("completed_at", ""),
            "frequency": meta.get("frequency", ""),
            "schedule": meta.get("schedule", ""),
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
    entry["last_viewed"] = datetime.now().isoformat()
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
