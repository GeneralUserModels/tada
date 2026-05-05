"""Filesystem helpers for the topic-grouped tada layout."""

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


def _split_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    body_start = text.find("\n", end + 4)
    body = text[body_start + 1:] if body_start != -1 else ""
    frontmatter: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()
    return frontmatter, body


def _render_frontmatter(fm: dict[str, str], body: str) -> str:
    order = ["title", "description", "cadence", "schedule", "trigger", "confidence", "usefulness"]
    lines = ["---"]
    emitted: set[str] = set()
    for key in order:
        value = fm.get(key)
        if value is not None and value != "":
            lines.append(f"{key}: {value}")
            emitted.add(key)
    for key in sorted(k for k in fm if k not in emitted and k != "frequency"):
        value = fm[key]
        if value != "":
            lines.append(f"{key}: {value}")
    lines.extend(["---", ""])
    return "\n".join(lines) + body


def migrate_moments_to_cadence(tada_dir: Path) -> int:
    """Rewrite accepted moment/state schema from frequency to cadence."""
    if not tada_dir.exists():
        return 0
    changed = 0
    for md in list_task_files(tada_dir):
        text = md.read_text()
        parsed = _split_frontmatter(text)
        if parsed is None:
            continue
        fm, body = parsed
        if "cadence" in fm:
            continue
        frequency = fm.pop("frequency", "")
        if fm.get("trigger"):
            fm["cadence"] = "trigger"
            fm.pop("schedule", None)
        elif frequency in ("daily", "weekly"):
            fm["cadence"] = "scheduled"
        else:
            fm["cadence"] = "once"
            fm.pop("schedule", None)
        md.write_text(_render_frontmatter(fm, body))
        changed += 1

    state_path = tada_dir / "results" / "_moment_state.json"
    if state_path.exists():
        import json

        state = json.loads(state_path.read_text())
        state_changed = False
        for entry in state.values():
            if "frequency_override" in entry:
                old = entry.pop("frequency_override")
                entry["cadence_override"] = "scheduled" if old in ("daily", "weekly") else old
                state_changed = True
        if state_changed:
            state_path.write_text(json.dumps(state, indent=2))
            changed += 1
    return changed


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


def list_active_task_files(tada_dir: Path) -> list[Path]:
    """Task .md files that have been executed (have a results dir) and are not dismissed.

    "Active" = the slug appears under `logs-tada/results/<slug>/` AND the slug's
    state in `_moment_state.json` does not have `dismissed: true`. Used by
    discovery/promotion/triggers — they should only consider tasks the user has
    actually engaged with.
    """
    from apps.moments.core.state import load_state

    if not tada_dir.exists():
        return []
    results_dir = tada_dir / "results"
    if not results_dir.exists():
        return []

    moment_state = load_state(tada_dir)
    active: list[Path] = []
    for md in list_task_files(tada_dir):
        slug = md.stem
        if not (results_dir / slug).is_dir():
            continue
        if moment_state.get(slug, {}).get("dismissed"):
            continue
        active.append(md)
    return active


def snapshot_tada_mtimes(tada_dir: Path) -> dict[str, float]:
    """Map slug → mtime for every active (executed + non-dismissed) tada task."""
    return {md.stem: md.stat().st_mtime for md in list_active_task_files(tada_dir)}


def summarize_tada_tasks(tada_dir: Path) -> str:
    """Render active (executed and not dismissed) tada tasks as a markdown listing.

    Each entry shows topic/slug, title, description, cadence, schedule, and trigger
    so the discovery agent can decide whether a new candidate would duplicate an
    existing task. Excludes tasks that have never been executed and tasks the user
    dismissed — proposing variants of those would not be useful.
    """
    from apps.moments.runtime.execute import _parse_frontmatter

    files = list_active_task_files(tada_dir)
    if not files:
        return "(no existing tasks yet)"

    lines: list[str] = []
    for md in files:
        fm = _parse_frontmatter(md.read_text())
        topic = get_topic(md, tada_dir) or "(flat)"
        slug = md.stem
        title = fm.get("title", slug)
        description = fm.get("description", "")
        cadence = fm.get("cadence", "?")
        schedule = fm.get("schedule", "—")
        trigger = fm.get("trigger") or "—"
        lines.append(
            f"- **{topic}/{slug}** — {title}\n"
            f"  {description}\n"
            f"  cadence: {cadence} | schedule: {schedule} | trigger: {trigger}"
        )
    return "\n".join(lines)
