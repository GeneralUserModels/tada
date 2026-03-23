"""Outlook Calendar MCP server — fetch upcoming events via Microsoft Graph."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RESULTS = 20


def _access_token() -> str:
    return json.load(open(os.environ["OUTLOOK_TOKEN_PATH"]))["access_token"]


mcp = FastMCP("powernap-outlook-calendar")


@mcp.tool()
def fetch_events(since: float | None = None) -> str:
    """Fetch upcoming Outlook Calendar events."""
    headers = {"Authorization": f"Bearer {_access_token()}", "Prefer": 'outlook.timezone="UTC"'}
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
        resp = requests.get(f"{GRAPH_BASE}/me/events", headers=headers, params=params, timeout=30)
    else:
        params = {
            "startDateTime": now.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": str(MAX_RESULTS),
            "$select": "id,subject,start,end,bodyPreview,location",
        }
        resp = requests.get(f"{GRAPH_BASE}/me/calendarView", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    events = resp.json().get("value", [])
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
