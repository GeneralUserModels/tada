"""WebSocket endpoint."""

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from user_models.inference import handle_prediction_request

logger = logging.getLogger(__name__)


async def ws_endpoint(websocket: WebSocket, state):
    await websocket.accept()
    state.ws_connections.add(websocket)
    logger.info(f"WebSocket connected ({len(state.ws_connections)} total)")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")
            if event == "request_prediction":
                await handle_prediction_request(state)
    except WebSocketDisconnect:
        pass
    finally:
        state.ws_connections.discard(websocket)
        logger.info(f"WebSocket disconnected ({len(state.ws_connections)} total)")
