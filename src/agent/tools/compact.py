import json
import time
from pathlib import Path
from typing import Callable

import litellm

from .base_tool import BaseTool


class CompactTool(BaseTool):
    def __init__(self, transcript_dir: Path, summarizer: Callable[[str], str], model: str = "anthropic/claude-sonnet-4-20250514"):
        """
        transcript_dir: where to save conversation transcripts.
        summarizer: callable(text) -> summary string (wraps the LLM call).
        model: model name for accurate token counting via litellm.
        """
        super().__init__("compress", "Manually compress conversation context.",
            {
                "type": "object",
                "properties": {}
            }
        )
        self._transcript_dir = transcript_dir
        self._summarizer = summarizer
        self._model = model

    def estimate_tokens(self, messages: list) -> int:
        return litellm.token_counter(model=self._model, messages=messages)

    def microcompact(self, messages: list):
        """Clear old tool_result content in-place, keeping the last 3."""
        tool_results = []
        for msg in messages:
            if msg["role"] == "user" and isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        tool_results.append(part)
        if len(tool_results) <= 3:
            return
        for part in tool_results[:-3]:
            if isinstance(part.get("content"), str) and len(part["content"]) > 100:
                part["content"] = "[cleared]"

    def auto_compact(self, messages: list) -> list:
        """Save transcript, summarize, return compressed 2-message replacement."""
        self._transcript_dir.mkdir(exist_ok=True)
        path = self._transcript_dir / f"transcript_{int(time.time())}.jsonl"
        with open(path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg, default=str) + "\n")
        conv_text = json.dumps(messages, default=str)[:80000]
        summary = self._summarizer(
            "You are compacting a conversation between a user and an AI agent. "
            "Your job is to produce a summary that lets the agent continue seamlessly "
            "as if the conversation never reset.\n\n"
            "Include ALL of the following in your summary:\n"
            "1. **User's original request** — what the user asked for, in their words.\n"
            "2. **Current plan and progress** — the plan summary and all todo items with their "
            "IDs and statuses. Reproduce the plan state verbatim so it can be restored.\n"
            "3. **Key decisions and context** — any choices made, constraints discovered, "
            "or user preferences expressed (e.g. 'user said not to use X').\n"
            "4. **Files read and modified** — list every file path that was read or edited, "
            "with a one-line note on what was done or learned from each.\n"
            "5. **Errors encountered** — any errors hit and how they were resolved "
            "(or if they're still unresolved).\n"
            "6. **Pending work** — what the agent should do next, as specifically as possible.\n"
            "7. **Important code snippets** — any small but critical code (function signatures, "
            "config values, key lines) that the agent will need to reference.\n\n"
            "Be thorough but concise. Use bullet points. Do NOT omit file paths or error details "
            "— these are the hardest to recover after compaction.\n\n"
            f"Conversation to summarize:\n{conv_text}"
        )
        original_instruction = messages[0] if messages else None
        compacted = []
        if original_instruction:
            compacted.append(original_instruction)
        compacted.append({"role": "user", "content": f"[Compressed. Transcript: {path}]\n{summary}"})
        return compacted

    def run(self, **kwargs):
        """Called by agent loop with messages passed directly, not via schema."""
        return "Compress triggered. Agent loop handles message replacement."
