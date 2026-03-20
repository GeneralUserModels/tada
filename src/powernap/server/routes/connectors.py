"""GET/PUT /api/connectors/{name} — query and toggle connector enabled state."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorUpdate(BaseModel):
    enabled: bool


@router.get("")
async def get_connectors(request: Request):
    state = request.app.state.server
    return {
        name: {"enabled": not conn.paused}
        for name, conn in state.connectors.items()
    }


@router.put("/{name}")
async def update_connector(name: str, update: ConnectorUpdate, request: Request):
    state = request.app.state.server
    connector = state.connectors.get(name)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")
    if update.enabled:
        connector.resume()
        if name in state.config.disabled_connectors:
            state.config.disabled_connectors.remove(name)
    else:
        connector.pause()
        if name not in state.config.disabled_connectors:
            state.config.disabled_connectors.append(name)
    state.config.save()
    return {"ok": True, "name": name, "enabled": update.enabled}
