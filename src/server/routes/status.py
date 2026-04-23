"""GET /api/status — full server status."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.server
    model = state.model
    screen = state.connectors.get("screen")
    status = {
        "recording_active": screen is not None and not screen.paused,
        "training_active": model.training_active,
        "latest_scores": model.latest_scores,
        "sse_connections": len(state.sse_queues),
        "services_started": state.services_started,
        "current_activity": state.current_activity,
    }
    if model.data_manager is not None:
        status.update(model.data_manager.get_status())  # labels_processed
    if model.trainer is not None:
        status.update(model.trainer.get_status())       # step_count
    return status
