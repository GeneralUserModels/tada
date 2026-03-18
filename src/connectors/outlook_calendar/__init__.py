"""Outlook Calendar connector — fetches upcoming events via Microsoft Graph REST API."""

import logging
from datetime import datetime, timedelta, timezone

import requests

from connectors.base import TokenConnector

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class OutlookCalendarConnector(TokenConnector):
    def __init__(self, token_path: str, max_results: int = 20) -> None:
        super().__init__(token_path)
        self.max_results = max_results

    def fetch(self) -> list[dict]:
        """Fetch upcoming calendar events via the Microsoft Graph API."""
        headers = {"Authorization": f"Bearer {self._access_token()}", "Prefer": 'outlook.timezone="UTC"'}
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)
        params = {
            "startDateTime": now.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": str(self.max_results),
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
