"""Outlook Email MCP server — fetch recent inbox messages via Microsoft Graph."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import requests
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RESULTS = 100


def _access_token() -> str:
    return json.load(open(os.environ["OUTLOOK_TOKEN_PATH"]))["access_token"]


mcp = FastMCP("powernap-outlook-email")


@mcp.tool()
def fetch_emails(since: float | None = None) -> str:
    """Fetch recent Outlook inbox messages."""
    headers = {"Authorization": f"Bearer {_access_token()}"}
    filter_clause = "isDraft eq false"
    if since:
        since_dt = datetime.utcfromtimestamp(since).strftime("%Y-%m-%dT%H:%M:%SZ")
        filter_clause = f"isDraft eq false and receivedDateTime ge {since_dt}"
    params = {
        "$top": str(MAX_RESULTS),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,bodyPreview,receivedDateTime",
        "$filter": filter_clause,
    }
    resp = requests.get(f"{GRAPH_BASE}/me/messages", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    messages = resp.json().get("value", [])
    logger.info("outlook email: fetched %d messages", len(messages))
    return json.dumps([
        {
            "id": msg["id"],
            "subject": msg.get("subject", ""),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "snippet": msg.get("bodyPreview", ""),
            "date": msg.get("receivedDateTime", ""),
        }
        for msg in messages
    ])


if __name__ == "__main__":
    mcp.run(transport="stdio")
