"""Shared MCP resource-update notification loop for connector servers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from mcp.server.session import ServerSession


async def run_notify_loop(
    notify_event: asyncio.Event,
    get_session: Callable[[], ServerSession | None],
    resource_uri: str,
    log: logging.Logger,
) -> None:
    """Wait for notify_event, then push an MCP resource-updated notification.

    Loops forever; intended to run as an asyncio task for the lifetime of the server.
    """
    while True:
        await notify_event.wait()
        notify_event.clear()
        session = get_session()
        if session is not None:
            try:
                await session.send_resource_updated(resource_uri)
            except Exception:
                log.exception("failed to send resource updated notification")
