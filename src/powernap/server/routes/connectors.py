"""PUT /api/connectors/{name} — pause or resume a connector."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorUpdate(BaseModel):
    enabled: bool


@router.put("/{name}")
async def update_connector(name: str, update: ConnectorUpdate, request: Request):
    state = request.app.state.server
    connector = state.connectors.get(name)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")
    if update.enabled:
        connector.resume()
    else:
        connector.pause()
    return {"ok": True, "name": name, "enabled": update.enabled}
