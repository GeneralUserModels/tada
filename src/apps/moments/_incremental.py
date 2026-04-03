"""Helpers for incremental discovery: checkpoint I/O and session classification."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

SESSION_RE = re.compile(r"^session_(\d{8}_\d{6})$")
SESSION_TIME_FMT = "%Y%m%d_%H%M%S"
CHECKPOINT_TIME_FMT = "%Y-%m-%dT%H:%M:%S"


def read_checkpoint(checkpoint_path: Path) -> datetime | None:
    """Read the last-discovery timestamp from a checkpoint file. Returns None if missing."""
    if not checkpoint_path.exists():
        return None
    text = checkpoint_path.read_text().strip()
    if not text:
        return None
    return datetime.strptime(text, CHECKPOINT_TIME_FMT)


def write_checkpoint(checkpoint_path: Path) -> None:
    """Write the current time to the checkpoint file."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(datetime.now().strftime(CHECKPOINT_TIME_FMT) + "\n")


def classify_sessions(logs_dir: str, since: datetime | None) -> tuple[list[str], list[str]]:
    """Return (new_sessions, old_sessions) directory names, sorted chronologically.

    If since is None, all sessions are 'new' and old is empty.
    """
    logs_path = Path(logs_dir)
    all_sessions: list[tuple[datetime, str]] = []
    for entry in sorted(logs_path.iterdir()):
        if not entry.is_dir():
            continue
        m = SESSION_RE.match(entry.name)
        if m:
            ts = datetime.strptime(m.group(1), SESSION_TIME_FMT)
            all_sessions.append((ts, entry.name))

    all_sessions.sort(key=lambda x: x[0])

    if since is None:
        return [name for _, name in all_sessions], []

    new = [name for ts, name in all_sessions if ts > since]
    old = [name for ts, name in all_sessions if ts <= since]
    return new, old
