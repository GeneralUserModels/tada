"""Onboarding status and OS permission check endpoints."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Request
from server.services import start_services

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
    state.config.disabled_connectors.clear()
    state.config.save()
    asyncio.create_task(start_services(state))
    return {"ok": True}


@router.get("/permissions/notifications")
async def check_notifications():
    return {"granted": os.access(_NOTIFICATIONS_DB, os.R_OK)}


@router.get("/permissions/filesystem")
async def check_filesystem():
    # ~/Desktop etc. are always readable; test a TCC-protected path instead.
    try:
        os.listdir(Path.home() / "Library" / "Safari")
        return {"granted": True}
    except PermissionError:
        return {"granted": False}
    except FileNotFoundError:
        # Safari not installed — fall back to notification DB as a proxy
        return {"granted": os.access(_NOTIFICATIONS_DB, os.R_OK)}


@router.get("/permissions/browser_cookies")
async def check_browser_cookies():
    """Verify Chrome cookies work by making a real HTTP request to google.com."""
    import logging
    log = logging.getLogger("onboarding.browser_cookies")
    try:
        from pycookiecheat import chrome_cookies
        import requests
        cookie_dict = chrome_cookies("https://google.com")
        log.info("pycookiecheat returned %d cookies for google.com", len(cookie_dict))
        if not cookie_dict:
            log.info("no cookies found — reporting not granted")
            return {"granted": False}
        resp = requests.get("https://www.google.com", cookies=cookie_dict, timeout=5)
        # Google pages include "Sign in" when not authenticated
        authenticated = "Sign in" not in resp.text[:5000]
        log.info("google.com request status=%d authenticated=%s", resp.status_code, authenticated)
        return {"granted": authenticated}
    except Exception as e:
        log.warning("browser cookies check failed: %s", e)
        return {"granted": False}
