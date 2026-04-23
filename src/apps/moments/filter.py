"""Filter task definitions: read all candidates, rank them, copy the best N to logs-tada/."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint
from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model

_PROMPTS = Path(__file__).parent / "prompts"
INSTRUCTION_TEMPLATE = (_PROMPTS / "filter.txt").read_text()
INCREMENTAL_SECTION = (_PROMPTS / "filter_incremental.txt").read_text()


def _classify_candidates(dirs: list[str], since: datetime | None) -> tuple[list[str], list[str]]:
    """Return (new, old) candidate .md file paths based on mtime vs checkpoint."""
    all_files: list[tuple[float, str]] = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.glob("*.md"):
            all_files.append((f.stat().st_mtime, str(f)))
    all_files.sort(key=lambda x: x[0])
    if since is None:
        return [path for _, path in all_files], []
    cutoff = since.timestamp()
    new = [path for mtime, path in all_files if mtime > cutoff]
    old = [path for mtime, path in all_files if mtime <= cutoff]
    return new, old


def run(logs_dir: str, n: int = 10, model: str | None = None, api_key: str | None = None, on_round=None) -> str:
    logs_path = Path(logs_dir).resolve()
    tasks_dir = str(logs_path / "tasks")
    oneoffs_dir = str(logs_path / "oneoffs")
    tada_dir = str(logs_path.parent / "logs-tada")
    checkpoint_path = logs_path / "tasks" / ".last_filter"
    Path(tada_dir).mkdir(parents=True, exist_ok=True)
    model = model or resolve_moments_model()
    agent, _ = build_agent(model, logs_dir, api_key=api_key)
    agent.max_rounds = 50
    agent.on_round = on_round

    last_filter = read_checkpoint(checkpoint_path)
    new_candidates, old_candidates = _classify_candidates([tasks_dir, oneoffs_dir], last_filter)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(
        tasks_dir=tasks_dir, oneoffs_dir=oneoffs_dir, tada_dir=tada_dir, n=n
    )

    if last_filter is not None and new_candidates:
        new_list = "\n".join(f"- {p}" for p in new_candidates)
        old_list = "\n".join(f"- {p}" for p in old_candidates) if old_candidates else "- (none)"
        instruction += INCREMENTAL_SECTION.format(
            last_filter_date=last_filter.strftime("%Y-%m-%d %H:%M"),
            new_candidates_list=new_list,
            old_candidates_list=old_list,
        )
    elif last_filter is not None and not new_candidates:
        instruction += (
            f"\n\n## Note\n\nThe last filter was on "
            f"**{last_filter.strftime('%Y-%m-%d %H:%M')}** and there are no new candidates "
            f"since then. Review existing candidates and {tada_dir}/ for any missed tasks."
        )

    messages = [{"role": "user", "content": instruction}]
    result = agent.run(messages)

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter tasks: rank all candidates and copy the best N to logs-tada/")
    parser.add_argument("logs_dir", help="Path to the logs directory (e.g., logs/)")
    parser.add_argument("-n", "--num-tasks", type=int, default=10, help="Number of top tasks to keep (default: 10)")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    model = args.model or resolve_moments_model()

    result = run(args.logs_dir, n=args.num_tasks, model=model, api_key=resolve_moments_api_key())
    print(result)
