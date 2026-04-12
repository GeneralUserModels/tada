"""Connector routes — query and toggle connector enabled state.

Registered by server/app.py under /api/connectors.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.feature_flags import is_enabled

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Virtual audio connector names — map to the single "audio" backend connector
_AUDIO_VIRTUAL = {"microphone", "system_audio"}
_AUDIO_FEATURE_FLAGS = {
    "microphone": "connector_microphone",
    "system_audio": "connector_system_audio",
}


class ConnectorUpdate(BaseModel):
    enabled: bool


@router.get("")
async def get_connectors(request: Request):
    state = request.app.state.server
    config = state.config
    google_ok = bool(
        config.google_token_path and Path(config.google_token_path).exists()
    )
    outlook_ok = bool(
        config.outlook_token_path and Path(config.outlook_token_path).exists()
    )

    def _available(ra: str | None) -> bool:
        if ra == "google":
            return google_ok
        if ra == "outlook":
            return outlook_ok
        return True

    result = {}
    for name, conn in state.connectors.items():
        # Hide the real "audio" connector — it's exposed as virtual entries below
        if name == "audio":
            continue
        result[name] = {
            "enabled": not conn.paused,
            "available": _available(state.connector_auth.get(name)),
            "error": conn.error,
            "requires_auth": state.connector_auth.get(name),
        }

    # Add virtual audio connector entries
    audio_conn = state.connectors.get("audio")
    if audio_conn is not None:
        for vname in _AUDIO_VIRTUAL:
            if not is_enabled(config, _AUDIO_FEATURE_FLAGS[vname]):
                continue
            result[vname] = {
                "enabled": vname not in config.disabled_connectors,
                "available": True,
                "error": config.connector_errors.get(vname),
                "requires_auth": None,
            }

    return result


@router.put("/{name}")
async def update_connector(name: str, update: ConnectorUpdate, request: Request):
    state = request.app.state.server
    config = state.config

    # Handle virtual audio connectors
    if name in _AUDIO_VIRTUAL:
        audio_conn = state.connectors.get("audio")
        if audio_conn is None:
            raise HTTPException(status_code=404, detail=f"Audio connector not available")

        if update.enabled:
            if name in config.disabled_connectors:
                config.disabled_connectors.remove(name)
            config.connector_errors.pop(name, None)
        else:
            if name not in config.disabled_connectors:
                config.disabled_connectors.append(name)
        config.save()

        mic_on = "microphone" not in config.disabled_connectors
        sys_on = "system_audio" not in config.disabled_connectors
        # Was any source already on BEFORE this toggle?
        other = "system_audio" if name == "microphone" else "microphone"
        was_any_on = other not in config.disabled_connectors

        # Update env vars
        audio_conn._server_params.env["TADA_MIC_ENABLED"] = "1" if mic_on else "0"
        audio_conn._server_params.env["TADA_SYS_ENABLED"] = "1" if sys_on else "0"

        if not mic_on and not sys_on:
            # Both off — pause and clear session file (finalize)
            audio_conn.stop()
            audio_conn._server_params.env.pop("TADA_SESSION_FILE", None)
        else:
            # Create session file if this is the first source being enabled
            if not was_any_on:
                log_dir = config.log_dir or "./logs"
                transcript_dir = Path(log_dir) / "audio"
                transcript_dir.mkdir(parents=True, exist_ok=True)
                dt = datetime.now()
                session_file = transcript_dir / f"{dt.strftime('%Y-%m-%d_%H-%M-%S')}.md"
                session_file.write_text(f"# Audio Transcript — {dt.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                audio_conn._server_params.env["TADA_SESSION_FILE"] = str(session_file)

            # Restart: stop so the polling loop disconnects (in its own task),
            # then resume after a delay so it reconnects with updated env vars.
            audio_conn.stop()

            async def _delayed_resume():
                await asyncio.sleep(2)
                audio_conn.resume()

            asyncio.create_task(_delayed_resume())

        return {"ok": True, "name": name, "enabled": update.enabled}

    # Standard connector handling
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
