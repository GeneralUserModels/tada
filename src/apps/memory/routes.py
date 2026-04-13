"""REST API for the personal knowledge wiki."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/memory", tags=["memory"])

# Files that are not wiki pages
_SPECIAL_FILES = {"index.md", "log.md", "schema.md"}
_HIDDEN_RE = re.compile(r"^\.")


def _get_memory_dir(request: Request) -> Path:
    return Path(request.app.state.server.config.log_dir).resolve() / "memory"


def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from markdown text."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


@router.get("/pages")
async def list_pages(request: Request):
    """List all wiki pages with their frontmatter metadata."""
    memory_dir = _get_memory_dir(request)
    if not memory_dir.exists():
        return []

    pages = []
    for md_file in sorted(memory_dir.rglob("*.md")):
        rel = md_file.relative_to(memory_dir)

        # Skip special files, hidden files, and archive
        if str(rel) in _SPECIAL_FILES:
            continue
        if any(_HIDDEN_RE.match(part) for part in rel.parts):
            continue
        if rel.parts[0] == "_archive" if rel.parts else False:
            continue

        fm = _parse_frontmatter(md_file.read_text(errors="replace"))
        pages.append({
            "path": str(rel),
            "title": fm.get("title", rel.stem.replace("-", " ").title()),
            "confidence": float(fm["confidence"]) if "confidence" in fm else None,
            "last_updated": fm.get("last_updated"),
            "category": str(rel.parent) if str(rel.parent) != "." else None,
        })

    return pages


@router.get("/pages/{page_path:path}")
async def get_page(page_path: str, request: Request):
    """Return the raw markdown of a specific wiki page."""
    memory_dir = _get_memory_dir(request)
    target = (memory_dir / page_path).resolve()

    # Prevent path traversal
    if not str(target).startswith(str(memory_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    return PlainTextResponse(target.read_text(errors="replace"), media_type="text/markdown")


@router.get("/log")
async def get_log(request: Request):
    """Return the operations log."""
    memory_dir = _get_memory_dir(request)
    log_path = memory_dir / "log.md"
    if not log_path.exists():
        return PlainTextResponse("", media_type="text/markdown")
    return PlainTextResponse(log_path.read_text(errors="replace"), media_type="text/markdown")


@router.get("/index")
async def get_index(request: Request):
    """Return the wiki index."""
    memory_dir = _get_memory_dir(request)
    index_path = memory_dir / "index.md"
    if not index_path.exists():
        return PlainTextResponse("", media_type="text/markdown")
    return PlainTextResponse(index_path.read_text(errors="replace"), media_type="text/markdown")


@router.put("/pages/{page_path:path}")
async def update_page(page_path: str, request: Request):
    """Update the raw markdown of a specific wiki page."""
    memory_dir = _get_memory_dir(request)
    target = (memory_dir / page_path).resolve()

    if not str(target).startswith(str(memory_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    body = await request.json()
    target.write_text(body["content"])
    return {"ok": True}


@router.get("/status")
async def get_status(request: Request):
    """Return wiki status: last ingest/lint times and page count."""
    memory_dir = _get_memory_dir(request)

    def _read_ts(p: Path) -> str | None:
        if not p.exists():
            return None
        try:
            return datetime.fromisoformat(p.read_text().strip()).isoformat()
        except (ValueError, OSError):
            return None

    page_count = 0
    if memory_dir.exists():
        for md_file in memory_dir.rglob("*.md"):
            rel = md_file.relative_to(memory_dir)
            if str(rel) not in _SPECIAL_FILES and not any(_HIDDEN_RE.match(part) for part in rel.parts):
                page_count += 1

    return {
        "exists": memory_dir.exists(),
        "last_ingest": _read_ts(memory_dir / ".last_ingest"),
        "last_lint": _read_ts(memory_dir / ".last_lint"),
        "last_service_run": _read_ts(memory_dir / ".memory_last_run"),
        "page_count": page_count,
    }
