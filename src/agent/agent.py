from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import httpx
import litellm
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .tools.base_tool import BaseTool
from .tools.compact import CompactTool
from .tools.background import BackgroundManager
from .tools.todo import PlanState, PlanWriteTool, PlanUpdateTool

TOKEN_THRESHOLD = 64_000


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
        api_key: str | None = None,
        on_round: Callable[[int, int], None] | None = None,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_token: Callable[[str, int], None] | None = None,
        on_round_end: Callable[[int, bool], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        max_output_tokens: int | None = None,
    ):
        self.model = model
        self.api_key = api_key or None
        self.system_prompt = system_prompt
        self.max_rounds = max_rounds
        self.max_output_tokens = max_output_tokens
        self.on_round = on_round
        self.on_tool_call = on_tool_call
        self.on_token = on_token
        self.on_round_end = on_round_end
        self.should_stop = should_stop
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
        if self._tool_schemas:
            self._tool_schemas[-1]["cache_control"] = {"type": "ephemeral"}
        plan_tools = [t for t in tools if isinstance(t, (PlanWriteTool, PlanUpdateTool))]
        self._plan_state = plan_tools[0]._state if plan_tools else None

    def run(self, messages: list) -> str:
        rounds_without_plan = 0
        output_tokens_used = 0
        warned_80 = False
        warned_95 = False

        for round_num in range(self.max_rounds):
            if self.should_stop and self.should_stop():
                print(f"  [agent] stop requested before round {round_num+1}, exiting")
                return ""
            if self.on_round:
                try:
                    self.on_round(round_num + 1, self.max_rounds)
                except Exception as e:
                    print(f"  [on_round callback error] {e}")

            # compression
            if self._compact:
                self._compact.microcompact(messages)
                token_est = self._compact.estimate_tokens(messages)
                if token_est > TOKEN_THRESHOLD:
                    print(f"  [round {round_num+1}] compacting ({token_est} est tokens)")
                    messages[:] = self._compact.auto_compact(messages)

            # drain background notifications
            if self._bg:
                notifs = self._bg.drain()
                if notifs:
                    txt = "\n".join(f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs)
                    print(f"  [round {round_num+1}] {len(notifs)} background notification(s)")
                    messages.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})

            # ensure conversation ends with user/tool message (Anthropic rejects assistant-last)
            if messages and messages[-1].get("role") == "assistant":
                messages.append({"role": "user", "content": "Continue."})

            # LLM call
            print(f"  [round {round_num+1}/{self.max_rounds}] calling {self.model}...")
            if self.on_token:
                response = self._call_llm_streaming(messages, round_num)
            else:
                response = self._call_llm(messages)
            usage = getattr(response, "usage", None)
            if usage:
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
                if cache_read or cache_creation:
                    print(f"  [cache] read={cache_read} creation={cache_creation}")
                output_tokens_used += getattr(usage, "completion_tokens", 0) or 0
            choice = response.choices[0]
            assistant_msg = choice.message
            messages.append(assistant_msg.model_dump())

            # log assistant text if any
            if assistant_msg.content:
                print(f"  [assistant] {assistant_msg.content[:500]}")

            # pause_turn: search still running server-side, loop back
            if choice.finish_reason == "pause_turn":
                print("  > web_search: (searching...)")
                continue

            # partition tool calls into server-side (web_search) and local
            all_calls = assistant_msg.tool_calls or []
            server_calls = [c for c in all_calls if c.id.startswith("srvtoolu_")]
            local_calls = [c for c in all_calls if not c.id.startswith("srvtoolu_")]

            # strip server-side tool calls from the message — their results are already
            # baked into the model's response, and leaving them in causes the API to
            # expect tool_result blocks we don't have
            if server_calls:
                msg = messages[-1]
                msg["tool_calls"] = [c for c in (msg.get("tool_calls") or []) if not c.get("id", "").startswith("srvtoolu_")]
                if not msg["tool_calls"]:
                    msg.pop("tool_calls", None)
                for call in server_calls:
                    try:
                        args = json.loads(call.function.arguments)
                        print(f"  > {call.function.name} (server): {args.get('query', '')[:500]}")
                    except (json.JSONDecodeError, AttributeError):
                        args = {}
                        print(f"  > {call.function.name} (server)")
                    if self.on_tool_call:
                        try:
                            self.on_tool_call(call.function.name, args)
                        except Exception as e:
                            print(f"  [on_tool_call error] {e}")

            is_final_round = not local_calls
            if self.on_round_end:
                try:
                    self.on_round_end(round_num, is_final_round)
                except Exception as e:
                    print(f"  [on_round_end error] {e}")

            if is_final_round:
                print(f"  [round {round_num+1}] no tool calls, finishing (reason={choice.finish_reason})")
                return assistant_msg.content or ""

            # tool dispatch — subagent calls run in parallel, everything else sequential
            used_plan = False
            manual_compress = False
            subagent_calls = []
            sequential_calls = []

            for call in local_calls:
                name = call.function.name
                raw_args = call.function.arguments
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    output = f"Error: invalid JSON in tool call arguments: {raw_args[:500]}"
                    print(f"  > {name}: {output}")
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                    continue
                if name == "task":
                    subagent_calls.append((call, args))
                else:
                    sequential_calls.append((call, args))

            # run sequential tools
            for call, args in sequential_calls:
                name = call.function.name
                if name == "compress":
                    manual_compress = True
                args_summary = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v) for k, v in args.items()}
                print(f"  > {name}({json.dumps(args_summary, default=str)[:800]})")
                if self.on_tool_call:
                    try:
                        self.on_tool_call(name, args)
                    except Exception as e:
                        print(f"  [on_tool_call error] {e}")
                tool = self._tool_map.get(name)
                try:
                    output = tool.run(**args) if tool else f"Unknown tool: {name}"
                except Exception as e:
                    output = f"Error: {e}"
                    print(f"  > {name} ERROR: {e}")
                print(f"  > {name} result: {str(output)[:500]}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": str(output)})
                if name in ("PlanWrite", "PlanUpdate"):
                    used_plan = True

            # run subagent calls in parallel, staggered to avoid overloading the API
            if subagent_calls:
                print(f"  > launching {len(subagent_calls)} subagent(s) in parallel (staggered)")
                tool = self._tool_map.get("task")
                with ThreadPoolExecutor(max_workers=len(subagent_calls)) as pool:
                    futures = {}
                    for i, (call, args) in enumerate(subagent_calls):
                        args_summary = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v) for k, v in args.items()}
                        print(f"  > task({json.dumps(args_summary, default=str)[:800]})")
                        if self.on_tool_call:
                            try:
                                self.on_tool_call(call.function.name, args)
                            except Exception as e:
                                print(f"  [on_tool_call error] {e}")
                        if i > 0:
                            time.sleep(2)
                        futures[pool.submit(tool.run, **args)] = call
                    for future in as_completed(futures):
                        call = futures[future]
                        try:
                            output = future.result()
                        except Exception as e:
                            output = f"Error: {e}"
                            print(f"  > task ERROR: {e}")
                        print(f"  > task result: {str(output)[:500]}")
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": str(output)})

            # budget warnings — token-based when a budget is set, else turn-based
            if self.max_output_tokens:
                pct = output_tokens_used / self.max_output_tokens
                if pct >= 0.95 and not warned_95:
                    warned_95 = True
                    messages.append({"role": "user", "content": f"<error>You've used {output_tokens_used}/{self.max_output_tokens} output tokens. Stop calling tools and write your final answer NOW with whatever you have.</error>"})
                elif pct >= 0.8 and not warned_80:
                    warned_80 = True
                    messages.append({"role": "user", "content": f"<warning>You've used {int(pct*100)}% of your output token budget ({output_tokens_used}/{self.max_output_tokens}). Wrap up — finalize with minimal additional tool use.</warning>"})
            else:
                remaining = self.max_rounds - round_num - 1
                if remaining == int(self.max_rounds * 0.2):
                    messages.append({"role": "user", "content": f"<warning>You have {remaining} turns remaining out of {self.max_rounds}. Wrap up soon.</warning>"})
                elif remaining == 3:
                    messages.append({"role": "user", "content": f"<warning>Only {remaining} turns left. Finish now — write final output and stop.</warning>"})

            # plan nag
            rounds_without_plan = 0 if used_plan else rounds_without_plan + 1
            if self._plan_state and self._plan_state.items and rounds_without_plan >= 3:
                has_open = any(i["status"] != "completed" for i in self._plan_state.items)
                if has_open:
                    messages.append({"role": "user", "content": "<reminder>Update your plan.</reminder>"})

            # manual compress
            if manual_compress and self._compact:
                messages[:] = self._compact.auto_compact(messages)

        print(f"  [agent] max rounds ({self.max_rounds}) reached")
        return "(max rounds reached)"

    def _build_llm_kwargs(self, messages: list) -> dict:
        is_gemini = self.model.startswith("gemini/")
        cache_control = None if is_gemini else {"type": "ephemeral"}
        system_block = {"type": "text", "text": self.system_prompt}
        if cache_control:
            system_block["cache_control"] = cache_control
        system_blocks = [system_block]
        if self._plan_state and self._plan_state.items:
            system_blocks.append({"type": "text", "text": f"\n\n<current-plan>\n{self._plan_state.render()}\n</current-plan>"})
        # Cache the first user message (task instruction) — it stays constant across rounds
        conv_messages = list(messages)
        if conv_messages and conv_messages[0].get("role") == "user":
            first = conv_messages[0]
            content = first.get("content", "")
            if isinstance(content, str):
                cached_content = {"type": "text", "text": content}
                if cache_control:
                    cached_content["cache_control"] = cache_control
                conv_messages[0] = {**first, "content": [cached_content]}
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": system_blocks}] + conv_messages,
            tools=self._tool_schemas if self._tool_schemas else None,
            max_tokens=16000,
            metadata={"app": "agent"},
        )
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self._web_search_options:
            if self.model.startswith(("openai/", "gpt-", "o1-", "o3-", "o4-")):
                # OpenAI uses web search as a tool, not a top-level param
                ws_tool = {"type": "web_search_preview", "web_search_preview": self._web_search_options}
                if kwargs.get("tools"):
                    kwargs["tools"].append(ws_tool)
                else:
                    kwargs["tools"] = [ws_tool]
            else:
                kwargs["web_search_options"] = self._web_search_options
                # Gemini requires this when combining web search with function calling
                if self.model.startswith("gemini/"):
                    kwargs["include_server_side_tool_invocations"] = True
        return kwargs

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=3),
        retry=retry_if_exception_type((litellm.RateLimitError, litellm.APIConnectionError, litellm.InternalServerError, litellm.Timeout, httpx.ReadTimeout)),
    )
    def _call_llm(self, messages: list):
        return litellm.completion(**self._build_llm_kwargs(messages))

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=3),
        retry=retry_if_exception_type((litellm.RateLimitError, litellm.APIConnectionError, litellm.InternalServerError, litellm.Timeout, httpx.ReadTimeout)),
    )
    def _call_llm_streaming(self, messages: list, round_num: int):
        kwargs = self._build_llm_kwargs(messages)
        kwargs["stream"] = True
        chunks = []
        for chunk in litellm.completion(**kwargs):
            chunks.append(chunk)
            try:
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
            except (IndexError, AttributeError):
                text = None
            if text and self.on_token:
                try:
                    self.on_token(text, round_num)
                except Exception as e:
                    print(f"  [on_token error] {e}")
        return litellm.stream_chunk_builder(chunks, messages=kwargs["messages"])
