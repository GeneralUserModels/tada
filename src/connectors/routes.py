"""Connector routes — query and toggle connector enabled state.

Registered by server/app.py under /api/connectors.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorUpdate(BaseModel):
    enabled: bool


@router.get("")
async def get_connectors(request: Request):
    state = request.app.state.server
    google_ok = bool(
        state.config.google_token_path and Path(state.config.google_token_path).exists()
    )
    outlook_ok = bool(
        state.config.outlook_token_path and Path(state.config.outlook_token_path).exists()
    )

    def _available(ra: str | None) -> bool:
        if ra == "google":
            return google_ok
        if ra == "outlook":
            return outlook_ok
        return True

    return {
        name: {
            "enabled": not conn.paused,
            "available": _available(state.connector_auth.get(name)),
            "error": conn.error,
            "requires_auth": state.connector_auth.get(name),
        }
        for name, conn in state.connectors.items()
    }


@router.put("/{name}")
async def update_connector(name: str, update: ConnectorUpdate, request: Request):
    state = request.app.state.server
    connector = state.connectors.get(name)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")
    if update.enabled:
        connector.resume()  # also clears connector.error
        if name in state.config.disabled_connectors:
            state.config.disabled_connectors.remove(name)
        state.config.connector_errors.pop(name, None)
    else:
        connector.stop()
        if name not in state.config.disabled_connectors:
            state.config.disabled_connectors.append(name)
    state.config.save()
    return {"ok": True, "name": name, "enabled": update.enabled}


@router.get("/label-history")
async def get_label_history(request: Request, limit: int = 50):
    log_dir = Path(request.app.state.server.config.log_dir)
    entries = []
    for jsonl_path in log_dir.glob("*/filtered.jsonl"):
        for line in jsonl_path.read_text().splitlines():
            entry = json.loads(line)
            text = entry["text"] if entry.get("prediction_event") else f"[{entry.get('source_name', '')}] {entry['text']}"
            entries.append({"text": text, "timestamp": entry["timestamp"]})
    entries.sort(key=lambda e: e["timestamp"])
    return entries[-limit:]
