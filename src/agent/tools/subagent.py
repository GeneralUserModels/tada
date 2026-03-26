from __future__ import annotations

from typing import Callable

from .base_tool import BaseTool

EXPLORE_TOOLS = {"bash", "read_file"}
GENERAL_TOOLS = {"bash", "read_file", "write_file", "edit_file"}


class SubAgentTool(BaseTool):
    """Spawns a child agent with a restricted tool set."""

    def __init__(self, agent_factory: Callable, tools: list[BaseTool]):
        """
        agent_factory: callable(tools) -> Agent instance with a .run(prompt) method.
        tools: the full parent tool list to filter from.
        """
        super().__init__("task", "Spawn a subagent for isolated exploration or work.",
            {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The task for the child agent"
                    },
                    "agent_type": {
                        "type": "string",
                        "enum": ["Explore", "general-purpose"],
                        "description": "Explore = read-only tools, general-purpose = read + write tools"
                    }
                },
                "required": ["prompt"]
            }
        )
        self._agent_factory = agent_factory
        self._tools = {t.name: t for t in tools}

    def run(self, prompt: str, agent_type: str = "Explore"):
        allowed = EXPLORE_TOOLS if agent_type == "Explore" else GENERAL_TOOLS
        child_tools = [t for name, t in self._tools.items() if name in allowed]
        agent = self._agent_factory(child_tools)
        result = agent.run(prompt)
        return (result or "(no summary)")[:50000]
