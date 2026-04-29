"""Filesystem helpers for the topic-grouped tada layout.

Tasks live at `logs-tada/<topic>/<slug>.md`. Legacy flat `logs-tada/<slug>.md`
files are still recognized so the runtime keeps working until filter migrates
them. Results stay flat at `logs-tada/results/<slug>/`.
"""

from __future__ import annotations

from pathlib import Path

# Top-level dir names inside `logs-tada/` that are NOT topic folders.
_RESERVED_DIRS = {"results", "_backups", "_pre_refine"}


def _is_topic_dir(p: Path) -> bool:
    return p.is_dir() and p.name not in _RESERVED_DIRS and not p.name.startswith("_")


def list_task_files(tada_dir: Path) -> list[Path]:
    """Return every task .md under tada_dir, across topic subdirs and any
    legacy flat files. Sorted by path for stable iteration."""
    files: list[Path] = list(tada_dir.glob("*.md"))
    for sub in tada_dir.iterdir():
        if _is_topic_dir(sub):
            files.extend(sub.glob("*.md"))
    files.sort()
    return files


def find_task_md(tada_dir: Path, slug: str) -> Path | None:
    """Locate a task .md by slug, checking topic dirs first, then flat."""
    for sub in tada_dir.iterdir():
        if not _is_topic_dir(sub):
            continue
        candidate = sub / f"{slug}.md"
        if candidate.exists():
            return candidate
    flat = tada_dir / f"{slug}.md"
    return flat if flat.exists() else None


def get_topic(md_file: Path, tada_dir: Path) -> str:
    """Topic name for a task .md, derived from its parent dir. Empty string
    for legacy flat files sitting directly in tada_dir."""
    if md_file.parent == tada_dir:
        return ""
    return md_file.parent.name


def list_topics(tada_dir: Path) -> list[str]:
    """Return sorted list of topic folder names under tada_dir."""
    return sorted(p.name for p in tada_dir.iterdir() if _is_topic_dir(p))
