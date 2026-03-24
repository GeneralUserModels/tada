"""Filesystem MCP server — watch user directories for file changes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession
from pydantic import AnyUrl
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

WATCH_DIRS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]

_events: list[dict] = []
_lock = threading.Lock()
_observer: Observer | None = None
_active_session: ServerSession | None = None
_notify_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


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
        if _loop is not None and _notify_event is not None:
            _loop.call_soon_threadsafe(_notify_event.set)


async def _notify_loop() -> None:
    """Bridge task: wake on watchdog events, push MCP notification to subscribed client."""
    while True:
        await _notify_event.wait()  # type: ignore[union-attr]
        _notify_event.clear()  # type: ignore[union-attr]
        if _active_session is not None:
            try:
                await _active_session.send_resource_updated("filesystem://changes")
            except Exception:
                logger.exception("filesystem: failed to send resource updated notification")


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:  # type: ignore[type-arg]
    global _observer, _loop, _notify_event
    _loop = asyncio.get_running_loop()
    _notify_event = asyncio.Event()
    asyncio.create_task(_notify_loop(), name="filesystem-notifier")
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


@mcp._mcp_server.subscribe_resource()
async def _on_subscribe(_uri: AnyUrl) -> None:
    global _active_session
    _active_session = mcp._mcp_server.request_context.session


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
