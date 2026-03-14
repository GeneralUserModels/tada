"""Google Calendar connector — uses gws CLI to fetch upcoming events."""

import json
import subprocess
from datetime import datetime, timezone


def get_upcoming_events(gws_path: str, max_results: int = 20) -> list[dict]:
    """Fetch upcoming calendar events via the gws CLI."""
    now_iso = datetime.now(timezone.utc).isoformat()
    params = json.dumps({
        "calendarId": "primary",
        "maxResults": max_results,
        "timeMin": now_iso,
    })
    result = subprocess.run(
        [gws_path, "calendar", "events", "list",
         "--params", params, "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(result.stdout)
    events = data if isinstance(data, list) else data.get("items", data.get("events", []))
    return [
        {
            "id": evt.get("id", ""),
            "summary": evt.get("summary", ""),
            "start": evt.get("start", ""),
            "end": evt.get("end", ""),
            "description": evt.get("description", ""),
            "location": evt.get("location", ""),
        }
        for evt in events
    ]
