"""Google Calendar MCP server — fetch upcoming events via the Google Calendar REST API."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from connectors._http import google_get

logger = logging.getLogger(__name__)

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
MAX_RESULTS = 20


mcp = FastMCP("powernap-calendar")


@mcp.tool()
def fetch_events(since: float | None = None) -> str:
    """Fetch upcoming Google Calendar events."""
    params: dict = {
        "calendarId": "primary",
        "maxResults": MAX_RESULTS,
        "timeMin": datetime.now(timezone.utc).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    if since:
        params["updatedMin"] = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
    events = google_get(f"{CALENDAR_BASE}/calendars/primary/events", params).get("items", [])
    logger.info("calendar: fetched %d events", len(events))
    return json.dumps([
        {
            "id": evt.get("id", ""),
            "summary": evt.get("summary", ""),
            "start": evt.get("start", ""),
            "end": evt.get("end", ""),
            "description": evt.get("description", ""),
            "location": evt.get("location", ""),
        }
        for evt in events
    ])


if __name__ == "__main__":
    mcp.run(transport="stdio")
