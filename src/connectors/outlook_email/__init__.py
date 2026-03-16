"""Outlook Email connector — fetches recent messages via Microsoft Graph REST API."""

import json
import logging

import requests

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _read_access_token(token_path: str) -> str:
    with open(token_path) as f:
        return json.load(f)["access_token"]


def get_recent_emails(token_path: str, max_results: int = 100) -> list[dict]:
    """Fetch recent inbox emails via the Microsoft Graph API."""
    access_token = _read_access_token(token_path)
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "$top": str(max_results),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,bodyPreview,receivedDateTime",
        "$filter": "isDraft eq false",
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
