"""Gmail connector — uses gws CLI to fetch recent messages from primary inbox."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)


def get_recent_emails(gws_path: str, max_results: int = 100) -> list[dict]:
    """Fetch recent primary inbox emails via the gws CLI."""
    # List message IDs from primary inbox
    list_params = json.dumps({
        "userId": "me", "maxResults": max_results, "labelIds": ["INBOX"],
        "q": "-category:promotions -category:social",
    })
    result = subprocess.run(
        [gws_path, "gmail", "users", "messages", "list",
         "--params", list_params, "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    logger.info("gmail list stdout: %s", result.stdout[:500])
    if result.stderr:
        logger.warning("gmail list stderr: %s", result.stderr[:500])
    data = json.loads(result.stdout)
    msg_ids = [m["id"] for m in (data.get("messages") or [])]
    logger.info("gmail list returned %d message IDs", len(msg_ids))

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
        subject = headers.get("Subject", "")
        logger.info("gmail fetched email: %s", subject)
        emails.append({
            "id": msg_id,
            "subject": subject,
            "from": headers.get("From", ""),
            "snippet": msg.get("snippet", ""),
            "date": headers.get("Date", ""),
        })

    return emails
