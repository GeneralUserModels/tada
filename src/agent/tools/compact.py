import json
import time
from pathlib import Path
from typing import Callable

from .base_tool import BaseTool


class CompactTool(BaseTool):
    def __init__(self, transcript_dir: Path, summarizer: Callable[[str], str]):
        """
        transcript_dir: where to save conversation transcripts.
        summarizer: callable(text) -> summary string (wraps the LLM call).
        """
        super().__init__("compress", "Manually compress conversation context.",
            {
                "type": "object",
                "properties": {}
            }
        )
        self._transcript_dir = transcript_dir
        self._summarizer = summarizer

    def estimate_tokens(self, messages: list) -> int:
        return len(json.dumps(messages, default=str)) // 4

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
        summary = self._summarizer(f"Summarize for continuity:\n{conv_text}")
        return [
            {"role": "user", "content": f"[Compressed. Transcript: {path}]\n{summary}"},
            {"role": "assistant", "content": "Understood. Continuing with summary context."},
        ]

    def run(self, **kwargs):
        """Called by agent loop with messages passed directly, not via schema."""
        return "Compress triggered. Agent loop handles message replacement."
