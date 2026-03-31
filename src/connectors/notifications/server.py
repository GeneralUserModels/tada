"""Notifications MCP server — read recent macOS notification center notifications."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import plistlib
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession
from pydantic import AnyUrl
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from connectors._notify import run_notify_loop

logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.usernoted/db2/db"
)
LIMIT = 50
_MACOS_EPOCH_OFFSET = 978307200  # seconds between 2001-01-01 and Unix epoch

_observer: Observer | None = None
_active_session: ServerSession | None = None
_notify_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


class _DBHandler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if _loop is not None and _notify_event is not None:
            _loop.call_soon_threadsafe(_notify_event.set)


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:  # type: ignore[type-arg]
    global _observer, _loop, _notify_event
    _loop = asyncio.get_running_loop()
    _notify_event = asyncio.Event()
    asyncio.create_task(
        run_notify_loop(_notify_event, lambda: _active_session, "notifications://activity", logger),
        name="notifications-notifier",
    )
    db_dir = os.path.dirname(DB_PATH)
    if os.path.isdir(db_dir):
        _observer = Observer()
        _observer.schedule(_DBHandler(), db_dir, recursive=False)
        _observer.start()
    yield
    if _observer is not None:
        _observer.stop()
        _observer.join()


mcp = FastMCP("powernap-notifications", lifespan=lifespan)


@mcp._mcp_server.subscribe_resource()
async def _on_subscribe(_uri: AnyUrl) -> None:
    global _active_session
    _active_session = mcp._mcp_server.request_context.session


@mcp.tool()
def fetch_notifications(since: float | None = None) -> str:
    """Fetch recent macOS notification center notifications."""
    if not os.path.exists(DB_PATH):
        return json.dumps([])

    where_clause = "WHERE r.data IS NOT NULL"
    query_params: list = [LIMIT]
    if since:
        where_clause += " AND r.delivered_date > ?"
        query_params = [since - _MACOS_EPOCH_OFFSET, LIMIT]

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = conn.execute(
        f"""
        SELECT r.rec_id, a.identifier, r.data, r.delivered_date
        FROM record r JOIN app a ON r.app_id = a.app_id
        {where_clause}
        ORDER BY r.delivered_date DESC LIMIT ?
        """,
        query_params,
    )
    results = []
    for rec_id, app_id, data, delivered_date in rows:
        try:
            plist = plistlib.loads(data)
            req = plist.get("req", {})
            results.append({
                "id": rec_id,
                "app": app_id,
                "title": req.get("titl", ""),
                "body": req.get("body", ""),
                "subtitle": req.get("subt", ""),
                "timestamp": delivered_date,
            })
        except Exception:
            pass
    conn.close()
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
