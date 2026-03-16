"""Outlook Calendar connector — fetches upcoming events via Microsoft Graph REST API."""

import json
import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _read_access_token(token_path: str) -> str:
    with open(token_path) as f:
        return json.load(f)["access_token"]


def get_upcoming_events(token_path: str, max_results: int = 20) -> list[dict]:
    """Fetch upcoming calendar events via the Microsoft Graph API."""
    access_token = _read_access_token(token_path)
    headers = {"Authorization": f"Bearer {access_token}", "Prefer": 'outlook.timezone="UTC"'}
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=7)
    params = {
        "startDateTime": now.isoformat(),
        "endDateTime": end.isoformat(),
        "$top": str(max_results),
        "$select": "id,subject,start,end,bodyPreview,location",
    }
    resp = requests.get(f"{GRAPH_BASE}/me/calendarView", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    events = resp.json().get("value", [])
    logger.info("outlook calendar: fetched %d events", len(events))

    return [
        {
            "id": evt["id"],
            "summary": evt.get("subject", ""),
            "start": evt.get("start", {}).get("dateTime", ""),
            "end": evt.get("end", {}).get("dateTime", ""),
            "description": evt.get("bodyPreview", ""),
            "location": evt.get("location", {}).get("displayName", ""),
        }
        for evt in events
    ]
