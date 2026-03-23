"""Notifications MCP server — read recent macOS notification center notifications."""

from __future__ import annotations

import json
import logging
import os
import plistlib
import sqlite3

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.usernoted/db2/db"
)
LIMIT = 50
_MACOS_EPOCH_OFFSET = 978307200  # seconds between 2001-01-01 and Unix epoch

mcp = FastMCP("powernap-notifications")


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
