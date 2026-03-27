from __future__ import annotations

import json

import litellm
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .tools.base_tool import BaseTool
from .tools.compact import CompactTool
from .tools.background import BackgroundManager
from .tools.todo import TodoTool

TOKEN_THRESHOLD = 80_000


class Agent:
    def __init__(
        self,
        model: str,
        system_prompt: str,
        tools: list[BaseTool],
        compact_tool: CompactTool | None = None,
        bg_manager: BackgroundManager | None = None,
        max_rounds: int = 30,
        web_search: bool | dict = False,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.max_rounds = max_rounds
        self._compact = compact_tool
        self._bg = bg_manager
        if web_search is True:
            self._web_search_options = {"search_context_size": "medium"}
        elif isinstance(web_search, dict):
            self._web_search_options = web_search
        else:
            self._web_search_options = None
        self._tool_map = {t.name: t for t in tools}
        self._tool_schemas = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
            for t in tools
        ]
        self._todo = next((t for t in tools if isinstance(t, TodoTool)), None)

    def run(self, messages: list) -> str:
        rounds_without_todo = 0

        for _ in range(self.max_rounds):
            # compression
            if self._compact:
                self._compact.microcompact(messages)
                if self._compact.estimate_tokens(messages) > TOKEN_THRESHOLD:
                    messages[:] = self._compact.auto_compact(messages)

            # drain background notifications
            if self._bg:
                notifs = self._bg.drain()
                if notifs:
                    txt = "\n".join(f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs)
                    messages.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})

            # ensure conversation ends with user/tool message (Anthropic rejects assistant-last)
            if messages and messages[-1].get("role") == "assistant":
                messages.append({"role": "user", "content": "Continue."})

            # LLM call
            response = self._call_llm(messages)
            choice = response.choices[0]
            assistant_msg = choice.message
            messages.append(assistant_msg.model_dump())

            # pause_turn: search still running server-side, loop back
            if choice.finish_reason == "pause_turn":
                print("  > web_search: (searching...)")
                continue

            # partition tool calls into server-side (web_search) and local
            all_calls = assistant_msg.tool_calls or []
            server_calls = [c for c in all_calls if c.id.startswith("srvtoolu_")]
            local_calls = [c for c in all_calls if not c.id.startswith("srvtoolu_")]

            for call in server_calls:
                try:
                    args = json.loads(call.function.arguments)
                    print(f"  > {call.function.name} (server): {args.get('query', '')[:200]}")
                except (json.JSONDecodeError, AttributeError):
                    print(f"  > {call.function.name} (server)")

            if not local_calls:
                return assistant_msg.content or ""

            # tool dispatch
            used_todo = False
            manual_compress = False

            for call in local_calls:
                name = call.function.name
                args = json.loads(call.function.arguments)

                if name == "compress":
                    manual_compress = True

                tool = self._tool_map.get(name)
                try:
                    output = tool.run(**args) if tool else f"Unknown tool: {name}"
                except Exception as e:
                    output = f"Error: {e}"

                print(f"  > {name}: {str(output)[:200]}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": str(output)})

                if name == "TodoWrite":
                    used_todo = True

            # todo nag
            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if self._todo and self._todo.items and rounds_without_todo >= 3:
                has_open = any(i["status"] != "completed" for i in self._todo.items)
                if has_open:
                    messages.append({"role": "user", "content": "<reminder>Update your todos.</reminder>"})

            # manual compress
            if manual_compress and self._compact:
                messages[:] = self._compact.auto_compact(messages)

        return "(max rounds reached)"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((litellm.RateLimitError, litellm.APIConnectionError)),
    )
    def _call_llm(self, messages: list):
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": self.system_prompt}] + messages,
            tools=self._tool_schemas if self._tool_schemas else None,
            max_tokens=8000,
        )
        if self._web_search_options:
            kwargs["web_search_options"] = self._web_search_options
            # Gemini requires this when combining web search with function calling
            if self.model.startswith("gemini/"):
                kwargs["include_server_side_tool_invocations"] = True
        return litellm.completion(**kwargs)
