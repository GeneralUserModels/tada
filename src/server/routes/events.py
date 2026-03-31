"""GET /api/events — Server-Sent Events stream for real-time push."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api", tags=["events"])

logger = logging.getLogger(__name__)


@router.get("/events")
async def stream_events(request: Request):
    state = request.app.state.server

    async def generator():
        queue: asyncio.Queue = asyncio.Queue()
        state.sse_queues.add(queue)
        logger.info(f"SSE client connected ({len(state.sse_queues)} total)")
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await queue.get()
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            state.sse_queues.discard(queue)
            logger.info(f"SSE client disconnected ({len(state.sse_queues)} total)")

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
