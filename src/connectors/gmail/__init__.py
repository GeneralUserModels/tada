"""Gmail connector — uses gws CLI to fetch recent messages from primary inbox."""

import json
import subprocess


def get_recent_emails(gws_path: str, max_results: int = 20) -> list[dict]:
    """Fetch recent primary inbox emails via the gws CLI."""
    # List message IDs from primary inbox
    list_params = json.dumps({"userId": "me", "maxResults": max_results, "labelIds": ["CATEGORY_PERSONAL"]})
    result = subprocess.run(
        [gws_path, "gmail", "users", "messages", "list",
         "--params", list_params, "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(result.stdout)
    msg_ids = [m["id"] for m in (data.get("messages") or [])]

    # Fetch metadata for each message
    emails = []
    for msg_id in msg_ids:
        get_params = json.dumps({
            "userId": "me", "id": msg_id,
            "format": "metadata",
            "metadataHeaders": ["Subject", "From", "Date"],
        })
        result = subprocess.run(
            [gws_path, "gmail", "users", "messages", "get",
             "--params", get_params, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        msg = json.loads(result.stdout)
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        emails.append({
            "id": msg_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "snippet": msg.get("snippet", ""),
            "date": headers.get("Date", ""),
        })

    return emails
