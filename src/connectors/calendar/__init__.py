"""Google Calendar connector — fetches upcoming events via the Google Calendar REST API."""

import logging
from datetime import datetime, timezone

import requests

from connectors.base import TokenConnector

logger = logging.getLogger(__name__)

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarConnector(TokenConnector):
    def __init__(self, token_path: str, max_results: int = 20) -> None:
        super().__init__(token_path)
        self.max_results = max_results

    def fetch(self) -> list[dict]:
        """Fetch upcoming calendar events via the Google Calendar REST API."""
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        params = {
            "calendarId": "primary",
            "maxResults": self.max_results,
            "timeMin": datetime.now(timezone.utc).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        resp = requests.get(
            f"{CALENDAR_BASE}/calendars/primary/events",
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        events = resp.json().get("items", [])
        logger.info("calendar: fetched %d events", len(events))

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
