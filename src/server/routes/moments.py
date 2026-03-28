"""REST endpoints for moments (Ta-Da tab)."""

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from server.services.moments_executor import parse_frontmatter

router = APIRouter(prefix="/api/moments", tags=["moments"])


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
async def list_results(request: Request):
    """List completed moment results, sorted by most recent first."""
    results_dir = _get_tada_dir(request) / "results"
    if not results_dir.exists():
        return []
    results = []
    for meta_path in results_dir.glob("*/meta.json"):
        if not (meta_path.parent / "index.html").exists():
            continue
        meta = json.loads(meta_path.read_text())
        results.append({
            "slug": meta_path.parent.name,
            "title": meta.get("title", meta_path.parent.name),
            "description": meta.get("description", ""),
            "completed_at": meta.get("completed_at", ""),
            "frequency": meta.get("frequency", ""),
            "schedule": meta.get("schedule", ""),
        })
    results.sort(key=lambda r: r["completed_at"], reverse=True)
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
