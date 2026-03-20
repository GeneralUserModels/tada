"""Outlook Email connector — fetches recent messages via Microsoft Graph REST API."""

import logging
from datetime import datetime

import requests

from connectors.base import TokenConnector

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class OutlookEmailConnector(TokenConnector):
    def __init__(self, token_path: str, max_results: int = 100) -> None:
        super().__init__(token_path)
        self.max_results = max_results

    def fetch(self, since: float | None = None) -> list[dict]:
        """Fetch recent inbox emails via the Microsoft Graph API."""
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        filter_clause = "isDraft eq false"
        if since:
            since_dt = datetime.utcfromtimestamp(since).strftime("%Y-%m-%dT%H:%M:%SZ")
            filter_clause = f"isDraft eq false and receivedDateTime ge {since_dt}"
        params = {
            "$top": str(self.max_results),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,bodyPreview,receivedDateTime",
            "$filter": filter_clause,
        }
        resp = requests.get(f"{GRAPH_BASE}/me/messages", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        messages = resp.json().get("value", [])
        logger.info("outlook email: fetched %d messages", len(messages))

        return [
            {
                "id": msg["id"],
                "subject": msg.get("subject", ""),
                "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                "snippet": msg.get("bodyPreview", ""),
                "date": msg.get("receivedDateTime", ""),
            }
            for msg in messages
        ]
