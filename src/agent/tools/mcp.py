"""Agent tool that exposes MCP servers as callable tools."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .base_tool import BaseTool


class MCPSession:
    """Manages a persistent connection to a single MCP server."""

    def __init__(self, name: str, command: str, args: list[str], env: dict[str, str] | None = None):
        self.name = name
        merged_env = {**os.environ, **(env or {})}
        self._server_params = StdioServerParameters(command=command, args=args, env=merged_env)
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self.tools: list[dict] = []  # [{name, description, input_schema}]

    async def connect(self) -> None:
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(self._server_params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        result = await self._session.list_tools()
        self.tools = [
            {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
            for t in result.tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        result = await self._session.call_tool(tool_name, arguments)
        if result.isError:
            text = result.content[0].text if result.content else "unknown error"
            return f"Error: {text}"
        return result.content[0].text if result.content else ""

    async def disconnect(self) -> None:
        if self._stack:
            await self._stack.aclose()
        self._stack = None
        self._session = None


class MCPTool(BaseTool):
    """Lets the agent call tools on MCP servers defined in src/connectors."""

    def __init__(self, servers: list[dict]):
        """servers: list of dicts with keys: name, command, args, env (optional)."""
        super().__init__("call_mcp", "Call a tool on an MCP server.",
            {
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": "Name of the MCP server"
                    },
                    "tool": {
                        "type": "string",
                        "description": "Name of the tool to call"
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Arguments to pass to the tool"
                    }
                },
                "required": ["server", "tool"]
            }
        )
        self._server_defs = servers
        self._sessions: dict[str, MCPSession] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def connect_all(self) -> list[dict]:
        """Connect to all servers and return their tool listings.

        Returns a flat list of tool defs with an added 'server' field,
        suitable for including in the LLM's tool list.
        """
        return self._get_loop().run_until_complete(self._connect_all())

    async def _connect_all(self) -> list[dict]:
        all_tools = []
        for s in self._server_defs:
            session = MCPSession(s["name"], s["command"], s["args"], s.get("env"))
            await session.connect()
            self._sessions[s["name"]] = session
            for t in session.tools:
                all_tools.append({**t, "server": s["name"]})
        return all_tools

    def run(self, server: str, tool: str, arguments: dict | None = None):
        session = self._sessions.get(server)
        if not session:
            return f"Error: unknown server '{server}'"
        return self._get_loop().run_until_complete(session.call_tool(tool, arguments or {}))

    def shutdown(self) -> None:
        loop = self._get_loop()
        for session in self._sessions.values():
            loop.run_until_complete(session.disconnect())
        loop.close()
        self._loop = None
