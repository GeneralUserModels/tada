"""Analyze user activity logs to discover agent automation opportunities."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint, sessions_with_new_content
from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model

_PROMPTS = Path(__file__).parent / "prompts"
INSTRUCTION_TEMPLATE = (_PROMPTS / "discover.txt").read_text()
INCREMENTAL_SECTION = (_PROMPTS / "discover_incremental.txt").read_text()


def run(logs_dir: str, model: str, api_key: str | None = None, on_round=None) -> str:
    logs_path = Path(logs_dir).resolve()
    logs_dir = str(logs_path)
    checkpoint_path = logs_path / "tasks" / ".last_discovery"

    last_discovery = read_checkpoint(checkpoint_path)
    new_content_sessions = sessions_with_new_content(logs_dir, last_discovery)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir)

    if last_discovery is not None and new_content_sessions:
        sessions_list = "\n".join(f"- {s}/labels.jsonl" for s in new_content_sessions)
        instruction += INCREMENTAL_SECTION.format(
            last_discovery_date=last_discovery.strftime("%Y-%m-%d %H:%M"),
            sessions_with_new_content_list=sessions_list,
        )
    elif last_discovery is not None and not new_content_sessions:
        instruction += (
            f"\n\n## Note\n\nThe last discovery was on "
            f"**{last_discovery.strftime('%Y-%m-%d %H:%M')}** and there are no new labels "
            f"in any session since then. Analyze all existing sessions and non-session logs "
            f"(email, calendar, notifications, filesystem) thoroughly for tasks that may "
            f"have been missed."
        )

    agent, _ = build_agent(model, logs_dir, api_key=api_key)
    agent.max_rounds = 200
    agent.on_round = on_round
    messages = [{"role": "user", "content": instruction}]
    result = agent.run(messages)

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover agent tasks from activity logs")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    model = args.model or resolve_moments_model()

    result = run(args.logs_dir, model=model, api_key=resolve_moments_api_key())
    print(result)
