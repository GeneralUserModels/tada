"""ChatAgent — Agent subclass adapted for interactive chat with streaming."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import litellm

from agent.agent import Agent


class ChatAgent(Agent):
    """Agent adapted for interactive chat. Adds async streaming.

    No tools  → stripped-down agent, streams litellm directly.
    With tools → full agent, delegates to Agent.run() for tool loop.
    """

    def __init__(
        self,
        model: str,
        system_prompt: str,
        tools: list | None = None,
        api_key: str | None = None,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            tools=tools or [],
            api_key=api_key,
        )

    async def respond_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Stream one response turn.

        Args:
            messages: user/assistant turns only — system prompt is on the agent.

        Yields:
            Text tokens as they arrive.
        """
        if not self._tool_schemas:
            # No tools — stream directly from litellm
            system_msg = {"role": "system", "content": self.system_prompt}
            kwargs: dict = {
                "model": self.model,
                "messages": [system_msg] + list(messages),
                "stream": True,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        else:
            # Has tools — run inherited Agent.run() in thread (full tool loop)
            result = await asyncio.to_thread(self.run, list(messages))
            yield result
