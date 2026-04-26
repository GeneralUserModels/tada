"""Chat app service: disk persistence + agent factory.

Sessions live at <log_dir>/chats/<session_id>/{meta.json, messages.json}.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import litellm

from agent.builder import _ensure_sandbox_async
from agent.tools import (
    ALL_TOOLS,
    _bg_manager,
    BackgroundRunTool,
    BrowserClickTool,
    BrowserNavigateTool,
    BrowserReadTextTool,
    BrowserScreenshotTool,
    BrowserTypeTool,
    CheckBackgroundTool,
    EditTool,
    ReadTool,
    SkillTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    TerminalTool,
    WriteTool,
)
from agent.tools.compact import CompactTool
from chat import ChatAgent

# Effort caps the agent's *output* tokens (its generated text + tool-call args).
# This is a better proxy than turns for "how much agent work this response can
# do": a single turn can read a 50KB file or write a 10KB file, so turns
# under-count work; output tokens scale with what the agent actually produces.
EFFORT_TO_MAX_TOKENS = {"low": 5_000, "medium": 20_000, "high": 60_000}
DEFAULT_EFFORT = "medium"

# Hard safety cap on agent loop iterations. Tokens are the primary budget;
# this just prevents pathological infinite-tool-call loops.
SAFETY_MAX_ROUNDS = 40

AVAILABLE_MODELS = ["anthropic/claude-sonnet-4-6"]
DEFAULT_MODEL = AVAILABLE_MODELS[0]

_PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT_TEMPLATE = (_PROMPTS / "system.txt").read_text()

# Tool classes the chat agent gets — excludes plan tools, subagent.
_CHAT_TOOL_CLASSES = (
    ReadTool, WriteTool, EditTool, TerminalTool,
    SkillTool, BackgroundRunTool, CheckBackgroundTool,
    TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool,
    BrowserNavigateTool, BrowserReadTextTool, BrowserClickTool,
    BrowserTypeTool, BrowserScreenshotTool,
)


def chats_dir(state) -> Path:
    return Path(state.config.log_dir).resolve() / "chats"


def _session_dir(state, session_id: str) -> Path:
    return chats_dir(state) / session_id


def new_session_id() -> str:
    return f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_api_key(config) -> str | None:
    return config.agent_api_key or config.resolve_api_key("agent_api_key")


def list_sessions(state) -> list[dict]:
    cdir = chats_dir(state)
    if not cdir.exists():
        return []
    sessions = []
    for sdir in cdir.iterdir():
        if not sdir.is_dir() or not sdir.name.startswith("chat_"):
            continue
        meta_path = sdir / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        sessions.append(meta)
    sessions.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
    return sessions


def create_session(state, model: str, effort: str, title: str | None = None) -> dict:
    if model not in AVAILABLE_MODELS:
        model = DEFAULT_MODEL
    if effort not in EFFORT_TO_MAX_TOKENS:
        effort = DEFAULT_EFFORT
    sid = new_session_id()
    now = _now()
    meta = {
        "id": sid,
        "title": title or "New chat",
        "model": model,
        "effort": effort,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }
    sdir = _session_dir(state, sid)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "meta.json").write_text(json.dumps(meta, indent=2))
    (sdir / "messages.json").write_text("[]")
    return meta


def load_session(state, session_id: str) -> dict | None:
    sdir = _session_dir(state, session_id)
    if not sdir.exists():
        return None
    meta = json.loads((sdir / "meta.json").read_text())
    msgs_path = sdir / "messages.json"
    messages = json.loads(msgs_path.read_text()) if msgs_path.exists() else []
    return {"meta": meta, "messages": messages}


def save_session(state, session_id: str, meta: dict, messages: list[dict]) -> None:
    sdir = _session_dir(state, session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    meta = {**meta, "updated_at": _now(), "message_count": len(messages)}
    (sdir / "meta.json").write_text(json.dumps(meta, indent=2))
    (sdir / "messages.json").write_text(json.dumps(messages, indent=2, default=str))
    (sdir / "conversation.md").write_text(_render_markdown(meta, messages))


def _render_markdown(meta: dict, messages: list[dict]) -> str:
    """Render the chat as a clean User/Assistant transcript for other agents.

    Uses visible_messages so prelude prose (assistant turns with tool_calls)
    and tool-result messages are dropped — same view the user sees in the UI.
    """
    title = meta.get("title") or "Chat"
    started = meta.get("created_at", "")
    lines = [f"# {title}"]
    if started:
        lines.append(f"\n_Started: {started}_\n")
    for msg in visible_messages(messages):
        role = msg["role"]
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"**{speaker}:** {content}\n")
    return "\n".join(lines) + "\n"


def delete_session(state, session_id: str) -> bool:
    sdir = _session_dir(state, session_id)
    if not sdir.exists():
        return False
    shutil.rmtree(sdir)
    return True


def update_session_meta(state, session_id: str, **fields) -> dict | None:
    """Patch meta.json with the given fields (effort/title/etc)."""
    data = load_session(state, session_id)
    if data is None:
        return None
    meta = {**data["meta"], **fields, "updated_at": _now()}
    sdir = _session_dir(state, session_id)
    (sdir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


TITLE_MODEL = "gemini/gemini-3.1-flash-lite-preview"


async def generate_title(state, content: str) -> str:
    """Use Gemini Flash Lite to make a short title from the first user message."""
    api_key = state.config.default_llm_api_key or None
    snippet = content.strip()[:600]
    prompt = (
        "Write a concise 3-5 word title for a chat that starts with this user message. "
        "Output only the title — no quotes, no punctuation, no commentary.\n\n"
        f"Message: {snippet}"
    )
    kwargs = {
        "model": TITLE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 30,
        "metadata": {"app": "chat_title"},
    }
    if api_key:
        kwargs["api_key"] = api_key
    resp = await litellm.acompletion(**kwargs)
    title = (resp.choices[0].message.content or "").strip()
    title = title.strip("\"'`").strip()
    return title or "New chat"


# ── Visible-message extraction ──────────────────────────────────


def _flatten_text(content) -> str:
    """Content may be str or list of {type, text} blocks (Anthropic cache format)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
        return "\n".join(parts)
    return ""


_COMPACT_MARKER = "[Compressed. Transcript:"


def _is_compaction_artifact(text: str) -> bool:
    """Detect the synthetic message that CompactTool.auto_compact injects.

    auto_compact replaces the message list with [original_first_user, "[Compressed.
    Transcript: <path>]\\n<summary>"]. The model sometimes echoes that summary
    in its next response; either way we must hide it from the rendered chat.
    """
    return text.lstrip().startswith(_COMPACT_MARKER)


def visible_messages(messages: list[dict]) -> list[dict]:
    """Flatten the raw litellm message list into chat bubbles for the UI.

    Emits user messages and the *final* assistant message of each turn (the one
    with no `tool_calls`). Prelude prose — assistant messages that came with
    tool calls — is the agent's between-tool narration; it surfaces live in the
    progress preamble area, not as a persisted bubble. Tool-result messages
    and synthetic compaction wrappers are dropped entirely.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "user":
            text = _flatten_text(msg.get("content"))
            if _is_compaction_artifact(text):
                continue
            out.append({"role": "user", "content": text})
        elif role == "assistant":
            if msg.get("tool_calls"):
                continue
            content = _flatten_text(msg.get("content"))
            if not content.strip():
                continue
            if _is_compaction_artifact(content):
                continue
            out.append({"role": "assistant", "content": content})
    return out


# ── Tool-action formatter ────────────────────────────────────────


def _trim(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def format_tool_action(name: str, args: dict) -> str:
    """One-line human-readable description of a tool call."""
    a = args or {}
    if name == "read_file":
        return f"Read {_trim(a.get('path', ''), 80)}"
    if name == "write_file":
        return f"Wrote {_trim(a.get('path', ''), 80)}"
    if name == "edit_file":
        return f"Edited {_trim(a.get('path', ''), 80)}"
    if name == "bash":
        return f"Ran `{_trim(a.get('command', ''), 60)}`"
    if name == "browser_navigate":
        return f"Visited {_trim(a.get('url', ''), 80)}"
    if name == "browser_read_text":
        sel = a.get("selector")
        return f"Read page ({_trim(sel, 30)})" if sel else "Read page"
    if name == "browser_click":
        return f"Clicked {_trim(a.get('selector', ''), 40)}"
    if name == "browser_type":
        return f"Typed into {_trim(a.get('selector', ''), 40)}"
    if name == "browser_screenshot":
        return "Took screenshot"
    if name == "web_search":
        return f"Searched: {_trim(a.get('query', ''), 60)}"
    if name == "compress":
        return "Compressed conversation"
    if name == "background_run":
        return f"Started background: `{_trim(a.get('command', ''), 50)}`"
    if name == "check_background":
        return "Checked background task"
    if name == "task_create":
        return f"Created task: {_trim(a.get('title', a.get('content', '')), 60)}"
    if name == "task_update":
        return f"Updated task {_trim(a.get('id', ''), 20)}"
    if name == "task_get":
        return f"Read task {_trim(a.get('id', ''), 20)}"
    if name == "task_list":
        return "Listed tasks"
    if name == "load_skill":
        return f"Loaded skill {_trim(a.get('name', ''), 40)}"
    if name == "call_mcp":
        return f"Called MCP {_trim(a.get('tool', ''), 40)}"
    if name == "task":
        return f"Spawned subagent: {_trim(a.get('prompt', ''), 50)}"
    # Fallback
    summary = ", ".join(f"{k}={_trim(v, 30)}" for k, v in list(a.items())[:2])
    return f"{name}({summary})" if summary else name


# ── Agent factory ────────────────────────────────────────────────


def _make_summarizer(model: str, api_key: str | None):
    def summarize(text: str) -> str:
        kwargs = dict(
            model=model,
            messages=[{"role": "user", "content": text}],
            max_tokens=2000,
            metadata={"app": "chat_summarizer"},
        )
        if api_key:
            kwargs["api_key"] = api_key
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""
    return summarize


async def build_chat_agent(
    state,
    meta: dict,
    on_round: Callable[[int, int], None] | None = None,
    on_tool_call: Callable[[str, dict], None] | None = None,
    on_token: Callable[[str, int], None] | None = None,
    on_round_end: Callable[[int, bool], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ChatAgent:
    config = state.config
    model = meta.get("model", DEFAULT_MODEL)
    effort = meta.get("effort", DEFAULT_EFFORT)
    max_output_tokens = EFFORT_TO_MAX_TOKENS.get(effort, EFFORT_TO_MAX_TOKENS[DEFAULT_EFFORT])
    api_key = resolve_api_key(config)

    log_dir = str(Path(config.log_dir).resolve())
    await _ensure_sandbox_async([log_dir])

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(logs_dir=log_dir, max_tokens=max_output_tokens)

    transcript_dir = Path(log_dir) / "chats" / "_transcripts"
    compact_tool = CompactTool(transcript_dir, _make_summarizer(model, api_key), model=model)

    tools = [t for t in ALL_TOOLS if isinstance(t, _CHAT_TOOL_CLASSES)] + [compact_tool]

    return ChatAgent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        api_key=api_key,
        compact_tool=compact_tool,
        bg_manager=_bg_manager,
        max_rounds=SAFETY_MAX_ROUNDS,
        max_output_tokens=max_output_tokens,
        web_search=True,
        on_round=on_round,
        on_tool_call=on_tool_call,
        on_token=on_token,
        on_round_end=on_round_end,
        should_stop=should_stop,
    )
