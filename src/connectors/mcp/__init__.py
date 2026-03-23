"""MCPConnector — wraps any MCP server (local or community) as a powernap Connector."""

from __future__ import annotations

import json
import logging
import os
from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

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
    ) -> None:
        self._paused = False
        self.error: str | None = None
        # Merge full parent env with any connector-specific overrides.
        # MCP's stdio_client only inherits a minimal set (HOME, PATH, etc.) by default,
        # so without this, API keys and other env vars set in the server process are lost.
        merged_env = {**os.environ, **(env or {})}
        self._server_params = StdioServerParameters(command=command, args=args, env=merged_env)
        self._tool_name = tool_name
        self._exclude: set[str] = set(exclude_from_serialization or [])
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self, error: str | None = None) -> None:
        self._paused = True
        if error is not None:
            self.error = error

    async def stop(self, error: str | None = None) -> None:
        """Pause and disconnect the underlying subprocess immediately."""
        self.pause(error=error)
        await self._disconnect()

    def resume(self) -> None:
        self._paused = False
        self.error = None

    def serialize_item(self, item: dict) -> dict:
        return {k: v for k, v in item.items() if k not in self._exclude}

    async def fetch(self, since: float | None = None) -> list[dict]:
        if self._session is None:
            await self._connect()
        try:
            args = {"since": since} if since is not None else {}
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

    async def _connect(self) -> None:
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(self._server_params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
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
