"""Gmail MCP server — fetch recent inbox messages and track read events."""

from __future__ import annotations

import base64
import json
import logging
import os

import requests
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_RESULTS = 100
MAX_WATCH = 50

# Module-level state persists across tool calls for the lifetime of this process
_unread_watch: list[str] = []
_id_to_meta: dict[str, dict] = {}


def _access_token() -> str:
    return json.load(open(os.environ["GOOGLE_TOKEN_PATH"]))["access_token"]


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            body = _extract_body(part)
            if body:
                return body
    return ""


mcp = FastMCP("powernap-gmail")


@mcp.tool()
def fetch_emails(since: float | None = None) -> str:
    """Fetch new Gmail inbox messages and emit read events for previously-unread emails."""
    global _unread_watch, _id_to_meta
    headers = {"Authorization": f"Bearer {_access_token()}"}
    results = []

    # 1. Fetch new emails
    q = "-category:promotions -category:social"
    if since:
        q += f" after:{int(since)}"
    resp = requests.get(
        f"{GMAIL_BASE}/messages",
        headers=headers,
        params={"maxResults": MAX_RESULTS, "labelIds": "INBOX", "q": q},
        timeout=30,
    )
    resp.raise_for_status()
    msg_ids = [m["id"] for m in resp.json().get("messages") or []]
    logger.info("gmail list returned %d message IDs", len(msg_ids))

    for msg_id in msg_ids:
        msg_resp = requests.get(
            f"{GMAIL_BASE}/messages/{msg_id}",
            headers=headers,
            params={"format": "FULL"},
            timeout=30,
        )
        msg_resp.raise_for_status()
        msg = msg_resp.json()
        header_map = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        is_unread = "UNREAD" in msg.get("labelIds", [])
        subject = header_map.get("Subject", "")
        from_ = header_map.get("From", "")

        results.append({
            "id": msg_id,
            "event": "received",
            "subject": subject,
            "from": from_,
            "snippet": msg.get("snippet", ""),
            "date": header_map.get("Date", ""),
            "body": _extract_body(msg.get("payload", {})),
            "read": not is_unread,
        })

        if is_unread and msg_id not in _unread_watch:
            _unread_watch.append(msg_id)
            _id_to_meta[msg_id] = {"subject": subject, "from": from_}

    _unread_watch = _unread_watch[-MAX_WATCH:]

    # 2. Check watched unread emails for read events
    still_unread = []
    for msg_id in _unread_watch:
        msg_resp = requests.get(
            f"{GMAIL_BASE}/messages/{msg_id}",
            headers=headers,
            params={"format": "MINIMAL"},
            timeout=30,
        )
        if not msg_resp.ok:
            still_unread.append(msg_id)
            continue
        if "UNREAD" not in msg_resp.json().get("labelIds", []):
            meta = _id_to_meta.pop(msg_id, {})
            results.append({
                "id": f"{msg_id}_read",
                "event": "read",
                "message_id": msg_id,
                "subject": meta.get("subject", ""),
                "from": meta.get("from", ""),
            })
        else:
            still_unread.append(msg_id)

    _unread_watch = still_unread
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
