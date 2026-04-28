"""Agent builder: constructs configured Agent instances.

Importable without side effects — sandbox init happens lazily on first build.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import litellm
from sandbox_runtime import SandboxManager, SandboxRuntimeConfig

from .agent import Agent
from .tools import ALL_TOOLS, _bg_manager
from .tools.compact import CompactTool
from .tools.subagent import SubAgentTool
from .tools.todo import PlanState, PlanWriteTool, PlanUpdateTool

# Sandbox read-deny list shared by every agent built here and by
# ReadOnlyTerminalTool. Covers credentials plus macOS personal/app data the
# agent has no business scanning (iCloud Drive, Photos, Apple Music, Mail,
# Messages, sandboxed-app containers, etc.). Surgical rather than blanket
# `~/Library` because the packaged app's own data_dir lives under
# `~/Library/Application Support/tada`.
DENY_READ_PATHS = [
    "~/.ssh",
    "~/.gnupg",
    "~/.aws/credentials",
    "~/Library/Keychains",
    "~/Library/Cookies",
    "~/Library/Mobile Documents",
    "~/Library/CloudStorage",
    "~/Library/Photos",
    "~/Pictures",
    "~/Music",
    "~/Movies",
    "~/Library/Application Support/AddressBook",
    "~/Library/Safari",
    "~/Library/Containers",
    "~/Library/Group Containers",
]

_SYSTEM_PROMPT_TEMPLATE = """\
You are an agent with tools to read, write, edit files, run shell commands, search the web, and browse websites.

You can read project files and files the user explicitly references. You can write files to:
- {data_dir}/ (app data, logs, tasks)
- {tmp_dir}/ (temporary files)

You can browse the web using the browser_navigate, browser_read_text, browser_click, browser_type, and browser_screenshot tools. These use the user's Chrome cookies, so you can access authenticated pages (Twitter, Gmail, etc.). Use browser_read_text with a CSS selector to narrow down content on large pages.

When searching files via the terminal, prefer `rg` (ripgrep) over `grep`/`find` — it's installed, respects .gitignore, and is much faster. Use `rg --files | rg <pattern>` to find files by name.

Plan iteratively:
- Start by understanding the task, then use PlanWrite to outline your approach and steps.
- As you work, keep your plan current. Use PlanUpdate to add new steps you discover, remove steps that become unnecessary, and mark steps complete.
- If your approach changes significantly, use PlanWrite to revise the summary.
- The plan is a living document — update it as you learn more.

Use the task tool to spawn subagents for isolated exploration.
Be concise. Use tools proactively.
"""

_sandbox_initialized = False


def _ensure_sandbox(write_dirs: list[str]):
    global _sandbox_initialized
    if _sandbox_initialized:
        return
    asyncio.run(SandboxManager.initialize(SandboxRuntimeConfig(
        network={},
        filesystem={
            "allow_write": write_dirs + [tempfile.gettempdir()],
            "deny_read": DENY_READ_PATHS,
        },
    )))
    _sandbox_initialized = True


async def _ensure_sandbox_async(write_dirs: list[str]):
    global _sandbox_initialized
    if _sandbox_initialized:
        return
    await SandboxManager.initialize(SandboxRuntimeConfig(
        network={},
        filesystem={
            "allow_write": write_dirs + [tempfile.gettempdir()],
            "deny_read": DENY_READ_PATHS,
        },
    ))
    _sandbox_initialized = True


def _make_summarizer(model: str, api_key: str | None = None):
    def summarize(text: str) -> str:
        kwargs = dict(
            model=model,
            messages=[{"role": "user", "content": text}],
            max_tokens=2000,
            metadata={"app": "agent_summarizer"},
        )
        if api_key:
            kwargs["api_key"] = api_key
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""
    return summarize


def _make_child_agent(model: str, system_prompt: str, api_key: str | None = None):
    def factory(tools):
        return Agent(model=model, system_prompt=system_prompt, tools=tools, max_rounds=30, web_search=True, api_key=api_key)
    return factory


def build_agent(model: str, data_dir: str, extra_write_dirs: list[str] | None = None, api_key: str | None = None):
    """Build a fully configured Agent with all tools. Initializes sandbox on first call.

    Each agent gets its own PlanState so concurrent runs (e.g. multiple
    moments executing in parallel) don't clobber each other's plans. Other
    module-level managers (background processes, task store, browser, skills)
    remain shared — see notes in `agent/tools/__init__.py`.
    """
    data_dir = str(Path(data_dir).resolve())
    write_dirs = [data_dir] + [str(Path(d).resolve()) for d in (extra_write_dirs or [])]
    _ensure_sandbox(write_dirs)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(data_dir=data_dir, tmp_dir=tempfile.gettempdir())
    transcript_dir = Path(data_dir) / "transcripts"
    compact_tool = CompactTool(transcript_dir, _make_summarizer(model, api_key), model=model)

    # Per-agent plan state: substitute fresh PlanWrite/PlanUpdate tools so each
    # agent sees its own plan. The other tools in ALL_TOOLS are stateless or
    # safely shared.
    plan_state = PlanState()
    base_tools = [
        PlanWriteTool(plan_state) if isinstance(t, PlanWriteTool)
        else PlanUpdateTool(plan_state) if isinstance(t, PlanUpdateTool)
        else t
        for t in ALL_TOOLS
    ]
    subagent_tool = SubAgentTool(_make_child_agent(model, system_prompt, api_key), base_tools)
    all_tools = base_tools + [compact_tool, subagent_tool]
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=all_tools,
        compact_tool=compact_tool,
        bg_manager=_bg_manager,
        web_search=True,
        api_key=api_key,
    )
    return agent, compact_tool
