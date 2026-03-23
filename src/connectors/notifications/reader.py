"""Read recent notifications from macOS notification center SQLite DB."""

import os
import plistlib
import sqlite3

from connectors.base import Connector

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.usernoted/db2/db"
)


class NotificationsConnector(Connector):
    def __init__(self, limit: int = 50) -> None:
        super().__init__()
        self.limit = limit

    def fetch(self, since: float | None = None) -> list[dict]:
        """Read recent notifications from macOS notification center DB.

        Returns a list of dicts with keys: id, app, title, body, subtitle, timestamp.
        The timestamp is macOS absolute time (seconds since 2001-01-01).
        """
        if not os.path.exists(DB_PATH):
            return []

        # macOS absolute time starts at 2001-01-01; Unix epoch is 978307200s earlier
        _MACOS_EPOCH_OFFSET = 978307200
        where_clause = "WHERE r.data IS NOT NULL"
        query_params: list = [self.limit]
        if since:
            where_clause += " AND r.delivered_date > ?"
            query_params = [since - _MACOS_EPOCH_OFFSET, self.limit]

        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        rows = conn.execute(
            f"""
            SELECT r.rec_id, a.identifier, r.data, r.delivered_date
            FROM record r JOIN app a ON r.app_id = a.app_id
            {where_clause}
            ORDER BY r.delivered_date DESC LIMIT ?
            """,
            query_params,
        )
        results = []
        for rec_id, app_id, data, delivered_date in rows:
            try:
                plist = plistlib.loads(data)
                req = plist.get("req", {})
                results.append(
                    {
                        "id": rec_id,
                        "app": app_id,
                        "title": req.get("titl", ""),
                        "body": req.get("body", ""),
                        "subtitle": req.get("subt", ""),
                        "timestamp": delivered_date,
                    }
                )
            except Exception:
                pass
        conn.close()
        return results
