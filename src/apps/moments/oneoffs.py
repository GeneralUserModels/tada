"""Analyze user activity logs to discover one-off tasks the agent can help with right now."""

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
from apps.moments.paths import list_active_task_files, summarize_tada_tasks
from apps.moments.state import set_pending_update

_PROMPTS = Path(__file__).parent / "prompts"
INSTRUCTION_TEMPLATE = (_PROMPTS / "oneoffs.txt").read_text()
INCREMENTAL_SECTION = (_PROMPTS / "oneoffs_incremental.txt").read_text()


def _snapshot_tada_mtimes(tada_dir: Path) -> dict[str, float]:
    """Map slug → mtime for every active (executed + non-dismissed) tada task."""
    return {md.stem: md.stat().st_mtime for md in list_active_task_files(tada_dir)}


def run(logs_dir: str, model: str, api_key: str | None = None, on_round=None) -> str:
    logs_path = Path(logs_dir).resolve()
    logs_dir = str(logs_path)
    Path(logs_dir, "oneoffs").mkdir(parents=True, exist_ok=True)
    checkpoint_path = logs_path / "oneoffs" / ".last_discovery"
    tada_dir = logs_path.parent / "logs-tada"

    last_discovery = read_checkpoint(checkpoint_path)
    new_content_sessions = sessions_with_new_content(logs_dir, last_discovery)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing_tasks = summarize_tada_tasks(tada_dir)
    instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(
        logs_dir=logs_dir,
        existing_tasks=existing_tasks,
    )

    if last_discovery is not None and new_content_sessions:
        sessions_list = "\n".join(f"- {s}/labels.jsonl" for s in new_content_sessions)
        instruction += INCREMENTAL_SECTION.format(
            last_discovery_date=last_discovery.strftime("%Y-%m-%d %H:%M"),
            sessions_with_new_content_list=sessions_list,
        )
    elif last_discovery is not None and not new_content_sessions:
        instruction += (
            f"\n\n## Note\n\nThe last one-off discovery was on "
            f"**{last_discovery.strftime('%Y-%m-%d %H:%M')}** and there are no new labels "
            f"in any session since then. Analyze all existing sessions and non-session logs "
            f"(email, calendar, notifications, filesystem) thoroughly for tasks that may "
            f"have been missed."
        )

    pre_mtimes = _snapshot_tada_mtimes(tada_dir)

    agent, _ = build_agent(model, logs_dir, extra_write_dirs=[str(tada_dir)], api_key=api_key)
    agent.max_rounds = 200
    agent.on_round = on_round
    messages = [{"role": "user", "content": instruction}]
    result = agent.run(messages)

    post_mtimes = _snapshot_tada_mtimes(tada_dir)
    for slug, mtime in post_mtimes.items():
        if mtime > pre_mtimes.get(slug, 0):
            set_pending_update(tada_dir, slug, reason="oneoffs updated description")

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover one-off tasks from activity logs")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    model = args.model or resolve_moments_model()

    result = run(args.logs_dir, model=model, api_key=resolve_moments_api_key())
    print(result)
