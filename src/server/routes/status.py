"""GET /api/status — full server status."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.server
    return {
        "recording_active": state.recording_active,
        "training_active": state.training_active,
        "inference_active": state.inference_active,
        "aggregation_queue_size": state.aggregation_queue.qsize(),
        "label_queue_size": state.label_queue.qsize(),
        "context_buffer_size": len(state.context_buffer),
        "untrained_batches": state.untrained_batches,
        "labels_processed": state.labels_processed,
        "step_count": state.step_count,
        "latest_scores": state.latest_scores,
        "ws_connections": len(state.ws_connections),
    }
