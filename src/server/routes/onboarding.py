"""Onboarding status and OS permission check endpoints."""

import asyncio
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel
from server.services import start_services, _log_startup_failure
from connectors.screen.napsack.recorder import SCREEN_FRAME_HEARTBEAT

router = APIRouter(prefix="/api", tags=["onboarding"])


class OnboardingComplete(BaseModel):
    seen_steps: list[str] = []

_NOTIFICATIONS_DB = str(
    Path.home() / "Library" / "Group Containers"
    / "group.com.apple.usernoted" / "db2" / "db"
)

# Stale-frame threshold mirrors the limit baked into capture_active_monitor_as_data_url.
_FRAME_FRESH_S = 5.0


@router.get("/onboarding/status")
async def onboarding_status(request: Request):
    config = request.app.state.server.config
    return {
        "complete": config.onboarding_complete,
        "seen_steps": list(config.onboarding_steps_seen),
        "enabled_connectors": list(config.enabled_connectors),
    }


@router.post("/onboarding/finalize")
async def onboarding_finalize(request: Request):
    """Mark onboarding complete and ensure background services are running.

    Idempotent: calling this when services are already up (e.g. returning users
    whose lifespan auto-started everything) is a no-op via start_services'
    internal guard. The connector selection is persisted earlier via
    PUT /api/settings during the connectors step.
    """
    state = request.app.state.server
    state.config.onboarding_complete = True
    state.config.save()
    task = asyncio.create_task(start_services(state))
    task.add_done_callback(_log_startup_failure)
    return {"ok": True}


@router.post("/onboarding/complete")
async def onboarding_complete(body: OnboardingComplete, request: Request):
    """Record which intro pages the user has seen. Services were started by /finalize."""
    state = request.app.state.server
    merged = list(state.config.onboarding_steps_seen)
    for step_id in body.seen_steps:
        if step_id not in merged:
            merged.append(step_id)
    state.config.onboarding_steps_seen = merged
    state.config.save()
    return {"ok": True}


@router.get("/services/status")
async def services_status(request: Request):
    """Readiness probe for the getting_ready step's polling loop."""
    state = request.app.state.server
    try:
        st = os.stat(SCREEN_FRAME_HEARTBEAT)
        screen_frame_fresh = (time.time() - st.st_mtime) < _FRAME_FRESH_S
    except OSError:
        screen_frame_fresh = False
    service = state.tabracadabra_service
    # screen_paused: true when the connector is paused (toggled off or
    # error-paused). The boot gate uses this to skip the screen-frame check
    # rather than relying on the persisted `enabled_connectors` setting (which
    # loads async on the renderer and can be stale relative to runtime state).
    screen_conn = state.connectors.get("screen")
    screen_paused = screen_conn is None or screen_conn.paused
    return {
        "services_started": bool(state.services_started),
        "tabracadabra_ready": service is not None and service.is_ready(),
        "screen_frame_fresh": screen_frame_fresh,
        "screen_paused": screen_paused,
    }


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
