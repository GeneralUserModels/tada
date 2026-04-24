"""Onboarding status and OS permission check endpoints."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel
from server.services import start_services, _log_startup_failure

router = APIRouter(prefix="/api", tags=["onboarding"])


class OnboardingComplete(BaseModel):
    enabled_connectors: list[str] = []
    seen_steps: list[str] = []

_NOTIFICATIONS_DB = str(
    Path.home() / "Library" / "Group Containers"
    / "group.com.apple.usernoted" / "db2" / "db"
)


@router.get("/onboarding/status")
async def onboarding_status(request: Request):
    config = request.app.state.server.config
    return {
        "complete": config.onboarding_complete,
        "seen_steps": list(config.onboarding_steps_seen),
        "enabled_connectors": list(config.enabled_connectors),
    }


@router.post("/onboarding/complete")
async def onboarding_complete(body: OnboardingComplete, request: Request):
    state = request.app.state.server
    state.config.onboarding_complete = True
    state.config.enabled_connectors = body.enabled_connectors
    # Union-merge seen step IDs while preserving first-seen order.
    merged = list(state.config.onboarding_steps_seen)
    for step_id in body.seen_steps:
        if step_id not in merged:
            merged.append(step_id)
    state.config.onboarding_steps_seen = merged
    state.config.save()
    task = asyncio.create_task(start_services(state))
    task.add_done_callback(_log_startup_failure)
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
