"""GET /api/training/history — return persisted reward metrics."""

import json
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/history")
async def get_training_history(request: Request):
    state = request.app.state.server
    metrics_path = Path(state.config.log_dir) / "metrics.jsonl"
    if not metrics_path.exists():
        return []
    lines = metrics_path.read_text().strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]
