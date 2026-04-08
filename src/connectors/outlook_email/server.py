"""Outlook Email MCP server — fetch recent inbox messages via Microsoft Graph."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from connectors._http import outlook_get

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RESULTS = 100


mcp = FastMCP("tada-outlook-email")


@mcp.tool()
def fetch_emails(since: float | None = None) -> str:
    """Fetch recent Outlook inbox messages."""
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
    messages = outlook_get(f"{GRAPH_BASE}/me/messages", params).get("value", [])
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
