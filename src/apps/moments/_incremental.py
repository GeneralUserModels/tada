"""Helpers for incremental discovery: checkpoint I/O and session classification."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

SESSION_RE = re.compile(r"^session_(\d{8}_\d{6})$")
SESSION_TIME_FMT = "%Y%m%d_%H%M%S"
LABEL_TIME_FMT = "%Y-%m-%d_%H-%M-%S-%f"
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


def _last_label_time(labels_path: Path) -> datetime | None:
    """Read the last line of a labels.jsonl file and parse its start_time."""
    last_line = None
    for line in labels_path.open():
        line = line.strip()
        if line:
            last_line = line
    if last_line is None:
        return None
    entry = json.loads(last_line)
    st = entry.get("start_time")
    if not st:
        return None
    return datetime.strptime(st, LABEL_TIME_FMT)


def sessions_with_new_content(logs_dir: str, since: datetime | None) -> list[str]:
    """Return session directory names that have labels after *since*, sorted chronologically.

    If since is None, returns all session directories.
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
        return [name for _, name in all_sessions]

    result = []
    for _, name in all_sessions:
        labels_path = logs_path / name / "labels.jsonl"
        if not labels_path.exists():
            continue
        last_time = _last_label_time(labels_path)
        if last_time is not None and last_time > since:
            result.append(name)
    return result
