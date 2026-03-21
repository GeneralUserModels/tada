"""Gmail connector — fetches recent messages from the primary inbox via the Gmail REST API."""

import base64
import logging

import requests

from connectors.base import TokenConnector

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


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


class GmailConnector(TokenConnector):
    def __init__(self, token_path: str, max_results: int = 100, max_watch: int = 50) -> None:
        super().__init__(token_path)
        self.max_results = max_results
        self._max_watch = max_watch
        # IDs of emails we saw as UNREAD — checked each poll for read events
        self._unread_watch: list[str] = []
        # Cached metadata for watched emails so read events carry subject/from
        self._id_to_meta: dict[str, dict] = {}

    def fetch(self, since: float | None = None) -> list[dict]:
        """Fetch new inbox emails and emit read events for previously-unread emails."""
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        results = []

        # ── 1. Fetch new emails ──────────────────────────────────────────────
        q = "-category:promotions -category:social"
        if since:
            q += f" after:{int(since)}"
        resp = requests.get(
            f"{GMAIL_BASE}/messages",
            headers=headers,
            params={"maxResults": self.max_results, "labelIds": "INBOX", "q": q},
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

            logger.info("gmail fetched email: %s", subject)
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

            if is_unread and msg_id not in self._unread_watch:
                self._unread_watch.append(msg_id)
                self._id_to_meta[msg_id] = {"subject": subject, "from": from_}

        # Keep watch list bounded
        self._unread_watch = self._unread_watch[-self._max_watch:]

        # ── 2. Check watched unread emails for read events ───────────────────
        still_unread = []
        for msg_id in self._unread_watch:
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
                meta = self._id_to_meta.pop(msg_id, {})
                logger.info("gmail read event: %s", meta.get("subject", msg_id))
                results.append({
                    "id": f"{msg_id}_read",
                    "event": "read",
                    "message_id": msg_id,
                    "subject": meta.get("subject", ""),
                    "from": meta.get("from", ""),
                })
            else:
                still_unread.append(msg_id)

        self._unread_watch = still_unread
        return results
