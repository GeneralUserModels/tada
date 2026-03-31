"""Onboarding status and OS permission check endpoints."""

import os
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["onboarding"])

_NOTIFICATIONS_DB = str(
    Path.home() / "Library" / "Group Containers"
    / "group.com.apple.usernoted" / "db2" / "db"
)


@router.get("/onboarding/status")
async def onboarding_status(request: Request):
    return {"complete": request.app.state.server.config.onboarding_complete}


@router.post("/onboarding/complete")
async def onboarding_complete(request: Request):
    state = request.app.state.server
    state.config.onboarding_complete = True
    state.config.save()
    return {"ok": True}


@router.get("/permissions/notifications")
async def check_notifications():
    return {"granted": os.access(_NOTIFICATIONS_DB, os.R_OK)}


@router.get("/permissions/filesystem")
async def check_filesystem():
    home = Path.home()
    granted = any(
        os.access(home / d, os.R_OK)
        for d in ("Desktop", "Documents", "Downloads")
    )
    return {"granted": granted}
