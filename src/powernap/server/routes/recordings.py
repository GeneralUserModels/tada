"""POST /api/recordings/aggregation — receive serialized aggregation data from client."""

import base64
import io
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


class AggregationPayload(BaseModel):
    """Serialized ProcessedAggregation from the Electron client."""
    screenshot_b64: str | None = None  # PNG image as base64
    events: list = []
    timestamp: float = 0.0
    end_timestamp: float = 0.0
    reason: str = ""
    event_type: str = ""
    request_state: str = ""
    screenshot_timestamp: float = 0.0
    end_screenshot_timestamp: float = 0.0
    monitor: dict = {}
    burst_id: str = ""
    scale_factor: float | None = 1.0


@router.post("/aggregation")
async def receive_aggregation(payload: AggregationPayload, request: Request):
    """Receive a serialized aggregation from the Electron recording bridge."""
    state = request.app.state.server

    if not state.recording_active:
        return {"status": "ignored", "reason": "recording not active"}

    # Decode screenshot if present
    screenshot_pil = None
    if payload.screenshot_b64:
        from PIL import Image
        img_bytes = base64.b64decode(payload.screenshot_b64)
        screenshot_pil = Image.open(io.BytesIO(img_bytes))

    # Build a dict matching what the labeler expects
    agg_data = {
        "screenshot": screenshot_pil,
        "events": payload.events,
        "timestamp": payload.timestamp,
        "end_timestamp": payload.end_timestamp,
        "reason": payload.reason,
        "event_type": payload.event_type,
        "request_state": payload.request_state,
        "screenshot_timestamp": payload.screenshot_timestamp,
        "end_screenshot_timestamp": payload.end_screenshot_timestamp,
        "monitor": payload.monitor,
        "burst_id": payload.burst_id,
        "scale_factor": payload.scale_factor,
    }

    # Persist raw aggregation if configured
    config = state.config
    if config.save_recordings and screenshot_pil is not None:
        import json
        from pathlib import Path

        if state.recordings_dir is None:
            state.recordings_dir = Path(config.log_dir) / "recordings"
            state.recordings_dir.mkdir(parents=True, exist_ok=True)

        ts_str = f"{payload.timestamp:.3f}"
        screenshot_pil.save(state.recordings_dir / f"{ts_str}.png")

        meta = payload.model_dump(exclude={"screenshot_b64"})
        with open(state.recordings_dir / "aggregations.jsonl", "a") as f:
            f.write(json.dumps(meta) + "\n")

    await state.aggregation_queue.put(agg_data)
    return {"status": "ok"}
