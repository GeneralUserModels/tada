"""Filter task definitions and copy agent-completable ones to logs-tada/."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent, DEFAULT_MODEL

INSTRUCTION_TEMPLATE = """\
Filter task definitions: copy the good ones to {tada_dir}/.

## Agent capabilities (for judging whether a task is completable)

The agent that will execute these tasks can:
- Run shell commands on macOS (bash)
- Read/write/edit any local file
- Web search
- Browse websites with the user's Chrome cookies (GitHub, Gmail, Slack, etc.)
- Read local logs: notifications, calendar, email, filesystem changes, screen sessions

Every task is run as a one-shot execution (not a daemon). "Daily digest" means "generate one now."

## Steps

1. Run `ls {tasks_dir}/` to list all task files.
2. For EACH `.md` file, spawn a subagent using the `task` tool. The subagent should:
   - Read the file with read_file
   - Decide: keep or skip. Keep the task if it is (a) grounded in real user behavior, (b) genuinely useful, and (c) completable by the agent above. Skip it only if it is vague fluff, requires macOS accessibility/window-management APIs, or cannot produce any concrete output.
   - If keeping: copy the file exactly to {tada_dir}/<filename>.md using write_file
   - Return one line: "PASS: <title>" or "SKIP: <title> — <reason>"
3. Run `ls {tada_dir}/` to verify.
"""


def run(logs_dir: str, model: str = DEFAULT_MODEL) -> str:
    tasks_dir = str(Path(logs_dir).resolve() / "tasks")
    tada_dir = str(Path(logs_dir).resolve().parent / "logs-tada")
    Path(tada_dir).mkdir(parents=True, exist_ok=True)
    agent, _ = build_agent(model)
    agent.max_rounds = 50
    instruction = INSTRUCTION_TEMPLATE.format(tasks_dir=tasks_dir, tada_dir=tada_dir)
    messages = [{"role": "user", "content": instruction}]
    return agent.run(messages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter tasks and copy agent-completable ones to logs-tada/")
    parser.add_argument("logs_dir", help="Path to the logs directory (e.g., logs-app/)")
    parser.add_argument("-m", "--model", default=os.environ.get("POWERNAP_AGENT_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
    print(result)
