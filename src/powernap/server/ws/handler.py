"""WebSocket endpoint and broadcast helpers."""

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


async def ws_endpoint(websocket: WebSocket, state):
    """WebSocket connection handler. Accepts, registers, and listens for client messages."""
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
                # Import here to avoid circular imports
                from powernap.server.services.inference import handle_prediction_request
                await handle_prediction_request(state)
    except WebSocketDisconnect:
        pass
    finally:
        state.ws_connections.discard(websocket)
        logger.info(f"WebSocket disconnected ({len(state.ws_connections)} total)")


async def broadcast(state, event: str, data: dict):
    """Send an event to all connected WebSocket clients."""
    message = json.dumps({"event": event, **data})
    dead = []
    for ws in state.ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.ws_connections.discard(ws)
