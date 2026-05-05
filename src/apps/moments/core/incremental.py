"""Helpers for incremental discovery checkpoint I/O."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
