from __future__ import annotations

from typing import Callable

from .base_tool import BaseTool

EXCLUDED_TOOLS = {"task"}


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
                },
                "required": ["prompt"]
            }
        )
        self._agent_factory = agent_factory
        self._tools = {t.name: t for t in tools}

    def run(self, prompt: str, agent_type: str = "general-purpose"):
        child_tools = [t for name, t in self._tools.items() if name not in EXCLUDED_TOOLS]
        agent = self._agent_factory(child_tools)
        result = agent.run([{"role": "user", "content": prompt}])
        return (result or "(no summary)")[:50000]
