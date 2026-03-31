"""Agent builder: constructs configured Agent instances.

Importable without side effects — sandbox init happens lazily on first build.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import litellm
from sandbox_runtime import SandboxManager, SandboxRuntimeConfig

from .agent import Agent
from .tools import ALL_TOOLS, _bg_manager
from .tools.compact import CompactTool
from .tools.subagent import SubAgentTool

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

POWERNAP_DATA = str(Path.home() / "Library" / "Application Support" / "PowerNap")
POWERNAP_REPO = str(Path.home() / "Documents" / "NAP" / "powernap")
TRANSCRIPT_DIR = Path("/tmp/powernap_transcripts")

SYSTEM_PROMPT = f"""\
You are an agent with tools to read, write, edit files, run shell commands, search the web, and browse websites.

You can read any file on the system. You can write files to:
- {POWERNAP_DATA}/ (app data, logs, tasks)
- {POWERNAP_REPO}/ (project repo)
- /tmp/

You can browse the web using the browser_navigate, browser_read_text, browser_click, browser_type, and browser_screenshot tools. These use the user's Chrome cookies, so you can access authenticated pages (Twitter, Gmail, etc.). Use browser_read_text with a CSS selector to narrow down content on large pages.

Plan iteratively:
- Start by understanding the task, then use PlanWrite to outline your approach and steps.
- As you work, keep your plan current. Use PlanUpdate to add new steps you discover, remove steps that become unnecessary, and mark steps complete.
- If your approach changes significantly, use PlanWrite to revise the summary.
- The plan is a living document — update it as you learn more.

Use the task tool to spawn subagents for isolated exploration.
Be concise. Use tools proactively.
"""

_sandbox_initialized = False


def _ensure_sandbox():
    global _sandbox_initialized
    if _sandbox_initialized:
        return
    asyncio.run(SandboxManager.initialize(SandboxRuntimeConfig(
        network={},
        filesystem={"allow_write": [POWERNAP_DATA, POWERNAP_REPO]},
    )))
    _sandbox_initialized = True


async def _ensure_sandbox_async():
    global _sandbox_initialized
    if _sandbox_initialized:
        return
    await SandboxManager.initialize(SandboxRuntimeConfig(
        network={},
        filesystem={"allow_write": [POWERNAP_DATA, POWERNAP_REPO]},
    ))
    _sandbox_initialized = True


def _make_summarizer(model: str):
    def summarize(text: str) -> str:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": text}],
            max_tokens=2000,
        )
        return resp.choices[0].message.content or ""
    return summarize


def _make_child_agent(model: str, system_prompt: str):
    def factory(tools):
        return Agent(model=model, system_prompt=system_prompt, tools=tools, max_rounds=30, web_search=True)
    return factory


def build_agent(model: str = DEFAULT_MODEL):
    """Build a fully configured Agent with all tools. Initializes sandbox on first call."""
    _ensure_sandbox()
    compact_tool = CompactTool(TRANSCRIPT_DIR, _make_summarizer(model), model=model)
    subagent_tool = SubAgentTool(_make_child_agent(model, SYSTEM_PROMPT), ALL_TOOLS)
    all_tools = ALL_TOOLS + [compact_tool, subagent_tool]
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=all_tools,
        compact_tool=compact_tool,
        bg_manager=_bg_manager,
        web_search=True,
    )
    return agent, compact_tool
