"""REPL entrypoint: uv run python -m agent [--model MODEL] [QUERY]"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import asyncio

from dotenv import load_dotenv
import litellm
from sandbox_runtime import SandboxManager, SandboxRuntimeConfig

from .agent import Agent
from .tools import ALL_TOOLS, TOOL_MAP, _bg_manager, _task_manager
from .tools.compact import CompactTool
from .tools.subagent import SubAgentTool

load_dotenv()

POWERNAP_DATA = str(Path.home() / "Library" / "Application Support" / "PowerNap")
POWERNAP_REPO = str(Path.home() / "Documents" / "NAP" / "powernap")

asyncio.run(SandboxManager.initialize(SandboxRuntimeConfig(
    network={},
    filesystem={"allow_write": [POWERNAP_DATA, POWERNAP_REPO]},
)))

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"
TRANSCRIPT_DIR = Path("/tmp/powernap_transcripts")

SYSTEM_PROMPT = f"""\
You are an agent with tools to read, write, edit files, run shell commands, search the web, and browse websites.

You can read any file on the system. You can write files to:
- {POWERNAP_DATA}/ (app data, logs, tasks)
- {POWERNAP_REPO}/ (project repo)
- /tmp/

You can browse the web using the browser_navigate, browser_read_text, browser_click, browser_type, and browser_screenshot tools. These use the user's Chrome cookies, so you can access authenticated pages (Twitter, Gmail, etc.). Use browser_read_text with a CSS selector to narrow down content on large pages.

Before doing any work, always plan first:
1. Read relevant files to understand the current state
2. Use TodoWrite to break the task into steps and track progress
3. Only then start making changes, updating todos as you go

Use the task tool to spawn subagents for isolated exploration.
Be concise. Use tools proactively.
"""

SLASH_COMMANDS = {
    "/compact": "Compress conversation history",
    "/tasks":   "List persistent tasks",
    "/clear":   "Clear conversation history",
    "/model":   "Show current model",
    "/help":    "Show this help",
}


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


def _build_agent(model: str):
    compact_tool = CompactTool(TRANSCRIPT_DIR, _make_summarizer(model))
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


def main():
    parser = argparse.ArgumentParser(description="PowerNap agent")
    parser.add_argument("query", nargs="*", help="One-shot query (omit for REPL)")
    parser.add_argument("-m", "--model", default=os.environ.get("POWERNAP_AGENT_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    model = args.model
    agent, compact_tool = _build_agent(model)
    history: list = []

    # one-shot mode
    if args.query:
        query = " ".join(args.query)
        history.append({"role": "user", "content": query})
        result = agent.run(history)
        print(result)
        return

    # REPL
    print(f"PowerNap agent  model={model}")
    print(f"Commands: {', '.join(SLASH_COMMANDS)}  |  q to quit\n")

    while True:
        try:
            query = input("\033[36magent >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        stripped = query.strip()
        if not stripped:
            continue
        if stripped.lower() in ("q", "exit", "quit"):
            break

        # slash commands
        if stripped == "/compact":
            if history:
                print("[compacting...]")
                history[:] = compact_tool.auto_compact(history)
                print("[done]")
            else:
                print("Nothing to compact.")
            continue
        if stripped == "/tasks":
            print(_task_manager.list_all())
            continue
        if stripped == "/clear":
            history.clear()
            print("[history cleared]")
            continue
        if stripped == "/model":
            print(model)
            continue
        if stripped == "/help":
            for cmd, desc in SLASH_COMMANDS.items():
                print(f"  {cmd:12s} {desc}")
            continue

        history.append({"role": "user", "content": query})
        result = agent.run(history)
        print(f"\n{result}\n")


if __name__ == "__main__":
    main()
