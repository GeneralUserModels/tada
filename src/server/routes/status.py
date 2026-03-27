"""GET /api/status — full server status."""

import json
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.server
    return {
        "recording_active": state.recording_active,
        "training_active": state.training_active,
        "inference_active": state.inference_active,
        "context_buffer_size": len(state.context_buffer),
        "untrained_batches": state.label_queue.qsize(),
        "labels_processed": state.labels_processed,
        "step_count": state.step_count,
        "latest_scores": state.latest_scores,
        "ws_connections": len(state.ws_connections),
    }


@router.get("/label-history")
async def get_label_history(request: Request, limit: int = 50):
    """Return recent label entries from persisted JSONL files for UI seeding."""
    state = request.app.state.server
    log_dir = Path(state.config.log_dir)
    entries = []
    for jsonl_path in log_dir.glob("*/filtered.jsonl"):
        for line in jsonl_path.read_text().splitlines():
            entry = json.loads(line)
            text = entry["text"] if entry["prediction_event"] else f"[{entry['source_name']}] {entry['text']}"
            entries.append({"text": text, "timestamp": entry["timestamp"]})
    entries.sort(key=lambda e: e["timestamp"])
    return entries[-limit:]
