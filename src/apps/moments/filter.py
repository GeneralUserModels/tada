"""Filter task definitions: read all candidates, rank them, copy the best N to logs-tada/."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent

INSTRUCTION_TEMPLATE = """\
You are selecting the best {n} tasks from a pool of candidates. Read all of them, compare across \
the full set, and copy only the top {n} to {tada_dir}/.

## Source directories

- **Moments** (recurring tasks): {tasks_dir}/
- **One-offs** (situational tasks): {oneoffs_dir}/

## Agent capabilities (for judging whether a task is completable)

The agent that will execute these tasks can:
- Run shell commands on macOS (bash)
- Read/write/edit any local file
- Web search
- Browse websites with the user's Chrome cookies (GitHub, Gmail, Slack, etc.)
- Read local logs: notifications, calendar, email, filesystem changes, screen sessions

Every task is run as a one-shot execution (not a daemon). "Daily digest" means "generate one now."

## Steps

1. Run `ls {tasks_dir}/ {oneoffs_dir}/` to list all task files from both directories.
2. Read ALL `.md` files. Use subagents to read them in parallel — each subagent should read a \
batch of files and return a summary of each (title, source dir, what it does, and a 1-10 quality \
score based on: grounded in real behavior, genuinely useful, completable by the agent).
3. Compare across the full set. Rank all tasks and select the top {n}. Prefer diversity — avoid \
picking multiple tasks that do essentially the same thing. Skip tasks that are vague fluff, require \
macOS accessibility/window-management APIs, or cannot produce concrete output. Also skip any \
reactive or trigger-based tasks ("when X happens, do Y").
4. Copy exactly the top {n} task files to {tada_dir}/<filename>.md using write_file.
5. Print your final ranking with a one-line justification per task.
6. Run `ls {tada_dir}/` to verify.
"""


def run(logs_dir: str, n: int = 10, model: str = os.environ["POWERNAP_AGENT_MODEL"]) -> str:
    logs_path = Path(logs_dir).resolve()
    tasks_dir = str(logs_path / "tasks")
    oneoffs_dir = str(logs_path / "oneoffs")
    tada_dir = str(logs_path.parent / "logs-tada")
    Path(tada_dir).mkdir(parents=True, exist_ok=True)
    agent, _ = build_agent(model, logs_dir)
    agent.max_rounds = 50
    instruction = INSTRUCTION_TEMPLATE.format(
        tasks_dir=tasks_dir, oneoffs_dir=oneoffs_dir, tada_dir=tada_dir, n=n
    )
    messages = [{"role": "user", "content": instruction}]
    return agent.run(messages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter tasks: rank all candidates and copy the best N to logs-tada/")
    parser.add_argument("logs_dir", help="Path to the logs directory (e.g., logs/)")
    parser.add_argument("-n", "--num-tasks", type=int, default=10, help="Number of top tasks to keep (default: 10)")
    parser.add_argument("-m", "--model", default=os.environ["POWERNAP_AGENT_MODEL"])
    args = parser.parse_args()

    result = run(args.logs_dir, n=args.num_tasks, model=args.model)
    print(result)
