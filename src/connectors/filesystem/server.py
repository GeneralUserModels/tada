"""Filesystem MCP server — watch user directories for file changes."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

WATCH_DIRS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]

_events: list[dict] = []
_lock = threading.Lock()
_observer: Observer | None = None


class _Handler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        with _lock:
            _events.append({
                "type": event.event_type,
                "path": event.src_path,
                "timestamp": time.time(),
            })


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:  # type: ignore[type-arg]
    global _observer
    _observer = Observer()
    handler = _Handler()
    for d in WATCH_DIRS:
        if os.path.isdir(d):
            _observer.schedule(handler, d, recursive=False)
    _observer.start()
    yield
    _observer.stop()
    _observer.join()


mcp = FastMCP("powernap-filesystem", lifespan=lifespan)


@mcp.tool()
def fetch_changes(since: float | None = None) -> str:
    """Fetch recent filesystem changes on Desktop, Documents, and Downloads."""
    with _lock:
        events = _events.copy()
        _events.clear()
    result = []
    for e in events:
        key = hashlib.md5(f"{e['path']}:{e['type']}:{e['timestamp']}".encode()).hexdigest()
        result.append({**e, "id": key})
    return json.dumps(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
