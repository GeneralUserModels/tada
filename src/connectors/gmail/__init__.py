"""Gmail connector — fetches recent messages from the primary inbox via the Gmail REST API."""

import logging

import requests

from connectors.base import TokenConnector

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailConnector(TokenConnector):
    def __init__(self, token_path: str, max_results: int = 100) -> None:
        super().__init__(token_path)
        self.max_results = max_results

    def fetch(self, since: float | None = None) -> list[dict]:
        """Fetch recent primary inbox emails via the Gmail REST API."""
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        q = "-category:promotions -category:social"
        if since:
            q += f" after:{int(since)}"
        list_params = {
            "maxResults": self.max_results,
            "labelIds": "INBOX",
            "q": q,
        }
        resp = requests.get(f"{GMAIL_BASE}/messages", headers=headers, params=list_params, timeout=30)
        resp.raise_for_status()
        msg_ids = [m["id"] for m in resp.json().get("messages") or []]
        logger.info("gmail list returned %d message IDs", len(msg_ids))

        emails = []
        for msg_id in msg_ids:
            msg_resp = requests.get(
                f"{GMAIL_BASE}/messages/{msg_id}",
                headers=headers,
                params={"format": "METADATA", "metadataHeaders": ["Subject", "From", "Date"]},
                timeout=30,
            )
            msg_resp.raise_for_status()
            msg = msg_resp.json()
            header_map = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = header_map.get("Subject", "")
            logger.info("gmail fetched email: %s", subject)
            emails.append({
                "id": msg_id,
                "subject": subject,
                "from": header_map.get("From", ""),
                "snippet": msg.get("snippet", ""),
                "date": header_map.get("Date", ""),
            })

        return emails
