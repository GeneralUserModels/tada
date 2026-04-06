"""MCPConnector — wraps any MCP server (local or community) as a powernap Connector."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack

import anyio.lowlevel
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import ResourceUpdatedNotification
from pydantic import AnyUrl

logger = logging.getLogger(__name__)


class MCPConnector:
    """Connects to an MCP server process via stdio and exposes one tool as fetch()."""

    def __init__(
        self,
        command: str,
        args: list[str],
        tool_name: str,
        env: dict[str, str] | None = None,
        exclude_from_serialization: list[str] | None = None,
        subscribe_uri: str | None = None,
    ) -> None:
        self._paused = False
        self.error: str | None = None
        self._disconnect_event = asyncio.Event()
        # Merge full parent env with any connector-specific overrides.
        # MCP's stdio_client only inherits a minimal set (HOME, PATH, etc.) by default,
        # so without this, API keys and other env vars set in the server process are lost.
        merged_env = {**os.environ, **(env or {})}
        self._server_params = StdioServerParameters(command=command, args=args, env=merged_env)
        self._tool_name = tool_name
        self._exclude: set[str] = set(exclude_from_serialization or [])
        self._subscribe_uri = subscribe_uri
        self._notification_event: asyncio.Event | None = asyncio.Event() if subscribe_uri else None
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self, error: str | None = None) -> None:
        self._paused = True
        if error is not None:
            self.error = error

    def stop(self, error: str | None = None) -> None:
        """Pause and request disconnection (actual disconnect happens in the owning task)."""
        self.pause(error=error)
        self._disconnect_event.set()

    async def disconnect_if_needed(self) -> None:
        """Disconnect if a stop was requested.  Must be called from the same task that connected."""
        if self._disconnect_event.is_set():
            self._disconnect_event.clear()
            await self._disconnect()

    def resume(self) -> None:
        self._paused = False
        self.error = None

    def serialize_item(self, item: dict) -> dict:
        return {k: v for k, v in item.items() if k not in self._exclude}

    async def fetch(self, since: float | None = None, extra_args: dict | None = None) -> list[dict]:
        if self._session is None:
            await self._connect()
        try:
            args = {"since": since} if since is not None else {}
            if extra_args:
                args.update(extra_args)
            result = await self._session.call_tool(self._tool_name, args)  # type: ignore[union-attr]
            if result.isError:
                text = result.content[0].text if result.content else ""
                raise RuntimeError(f"MCP tool error: {text}")
            text = result.content[0].text if result.content else ""
            if not text:
                return []
            return json.loads(text)
        except Exception:
            await self._disconnect()
            raise

    async def wait_for_notification(self, timeout: float = 10.0) -> bool:
        """Block until the server pushes a resource-updated notification (or timeout).

        Returns True if notified, False on timeout or if a disconnect was requested.
        """
        if self._notification_event is None:
            raise RuntimeError("Notifications not enabled for this connector")
        notify_task = asyncio.ensure_future(self._notification_event.wait())
        disconnect_task = asyncio.ensure_future(self._disconnect_event.wait())
        done, pending = await asyncio.wait(
            [notify_task, disconnect_task],
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if self._disconnect_event.is_set():
            return False
        if self._notification_event.is_set():
            self._notification_event.clear()
            return True
        return False

    async def _message_handler(
        self,
        message: object,
    ) -> None:
        """Handle incoming server messages; set the notification event on resource updates."""
        await anyio.lowlevel.checkpoint()
        if self._notification_event is not None:
            # ServerNotification is a RootModel — the actual notification is at .root
            root = getattr(message, "root", message)
            if isinstance(root, ResourceUpdatedNotification):
                self._notification_event.set()

    async def connect(self) -> None:
        """Eagerly establish the MCP session (and subscription) if not already connected."""
        if self._session is None:
            await self._connect()

    async def _connect(self) -> None:
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(self._server_params))
        msg_handler = self._message_handler if self._notification_event is not None else None
        session = await self._stack.enter_async_context(ClientSession(read, write, message_handler=msg_handler))
        await session.initialize()
        self._session = session
        if self._subscribe_uri is not None:
            await session.subscribe_resource(AnyUrl(self._subscribe_uri))
        logger.info(
            "MCPConnector connected: %s %s",
            self._server_params.command,
            " ".join(self._server_params.args),
        )

    async def _disconnect(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None
