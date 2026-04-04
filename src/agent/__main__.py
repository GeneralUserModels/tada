"""REPL entrypoint: uv run python -m agent [--model MODEL] [QUERY]"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .builder import build_agent
from .tools import _task_manager

load_dotenv()

SLASH_COMMANDS = {
    "/compact": "Compress conversation history",
    "/tasks":   "List persistent tasks",
    "/clear":   "Clear conversation history",
    "/model":   "Show current model",
    "/help":    "Show this help",
}


def main():
    parser = argparse.ArgumentParser(description="PowerNap agent")
    parser.add_argument("query", nargs="*", help="One-shot query (omit for REPL)")
    parser.add_argument("-m", "--model", default=os.environ["POWERNAP_AGENT_MODEL"])
    parser.add_argument("--data-dir", default=os.environ.get("POWERNAP_DATA_DIR", "."))
    args = parser.parse_args()

    model = args.model
    agent, compact_tool = build_agent(model, args.data_dir)
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
