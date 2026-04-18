"""ChatSession — manages a multi-turn chat conversation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from .agent import ChatAgent


class ChatSession:
    """Manages conversation state on top of a ChatAgent.

    The session owns the message history (user/assistant turns).
    The agent owns the system prompt and response generation.
    """

    def __init__(
        self,
        agent: ChatAgent,
        done_marker: str | None = None,
        initial_user_message: str | None = None,
    ):
        self.agent = agent
        self.done_marker = done_marker
        self.messages: list[dict] = []
        if initial_user_message:
            self.messages.append({"role": "user", "content": initial_user_message})
        self.ended = False

    @property
    def active(self) -> bool:
        return not self.ended

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})

    async def respond_stream(self) -> AsyncIterator[str]:
        """Stream one response turn. Appends full response to messages when done."""
        full_text = ""
        async for token in self.agent.respond_stream(self.messages):
            full_text += token
            yield token
        self.messages.append({"role": "assistant", "content": full_text})
        if self.done_marker and self.done_marker in full_text:
            self.ended = True

    def respond(self) -> str:
        """Sync single-turn response (for CLI). Uses inherited Agent.run()."""
        result = self.agent.run(list(self.messages))
        self.messages.append({"role": "assistant", "content": result})
        if self.done_marker and self.done_marker in result:
            self.ended = True
        return result

    def display_text(self, text: str) -> str:
        """Strip done marker for display."""
        if self.done_marker:
            return text.replace(self.done_marker, "").strip()
        return text

    def visible_messages(self) -> list[dict]:
        """Messages with cleaned display text (done marker stripped)."""
        result = []
        for msg in self.messages:
            if msg["role"] == "assistant":
                result.append({"role": "assistant", "content": self.display_text(msg["content"])})
            else:
                result.append(msg)
        return result

    def to_markdown(self, assistant_label: str = "Assistant") -> str:
        """Export conversation as markdown."""
        lines = ["# Conversation\n"]
        for msg in self.messages:
            if msg["role"] == "assistant":
                text = self.display_text(msg["content"])
                lines.append(f"**{assistant_label}:** {text}\n")
            else:
                lines.append(f"**User:** {msg['content']}\n")
        return "\n".join(lines)

    def save(self, path: Path, assistant_label: str = "Assistant"):
        """Save conversation markdown to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(assistant_label))
