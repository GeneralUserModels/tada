"""Outlook Calendar MCP server — fetch upcoming events via Microsoft Graph."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP

from connectors._http import outlook_get

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RESULTS = 20


mcp = FastMCP("tada-outlook-calendar")


@mcp.tool()
def fetch_events(since: float | None = None) -> str:
    """Fetch upcoming Outlook Calendar events."""
    extra_headers = {"Prefer": 'outlook.timezone="UTC"'}
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=7)
    if since:
        since_dt = datetime.fromtimestamp(since, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_dt = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_dt = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "$top": str(MAX_RESULTS),
            "$select": "id,subject,start,end,bodyPreview,location",
            "$filter": (
                f"lastModifiedDateTime ge {since_dt}"
                f" and start/dateTime ge '{now_dt}'"
                f" and start/dateTime le '{end_dt}'"
            ),
        }
        data = outlook_get(f"{GRAPH_BASE}/me/events", params, extra_headers)
    else:
        params = {
            "startDateTime": now.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": str(MAX_RESULTS),
            "$select": "id,subject,start,end,bodyPreview,location",
        }
        data = outlook_get(f"{GRAPH_BASE}/me/calendarView", params, extra_headers)
    events = data.get("value", [])
    logger.info("outlook calendar: fetched %d events", len(events))
    return json.dumps([
        {
            "id": evt["id"],
            "summary": evt.get("subject", ""),
            "start": evt.get("start", {}).get("dateTime", ""),
            "end": evt.get("end", {}).get("dateTime", ""),
            "description": evt.get("bodyPreview", ""),
            "location": evt.get("location", {}).get("displayName", ""),
        }
        for evt in events
    ])


if __name__ == "__main__":
    mcp.run(transport="stdio")
