"""Lint and maintain the personal knowledge wiki."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint


LINT_TEMPLATE = (Path(__file__).parent / "prompts" / "lint.txt").read_text()


def run(
    logs_dir: str,
    model: str,
    api_key: str | None = None,
    on_round=None,
    subagent_model: str | None = None,
    subagent_api_key: str | None = None,
) -> str:
    logs_path = Path(logs_dir).resolve()
    memory_dir = logs_path / "memory"

    if not memory_dir.exists():
        return "Wiki directory does not exist yet. Run ingest first."

    checkpoint_path = memory_dir / ".last_lint"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + LINT_TEMPLATE.format(
        memory_dir=str(memory_dir),
    )

    agent, _ = build_agent(
        model, str(logs_path), api_key=api_key,
        subagent_model=subagent_model, subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = 100
    agent.on_round = on_round
    result = agent.run([{"role": "user", "content": instruction}])

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    import logging

    from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model
    from server.cost_tracker import init_cost_tracking

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Lint and maintain the personal knowledge wiki")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    tracker = init_cost_tracking()

    model = args.model or resolve_moments_model()
    api_key = args.api_key or resolve_moments_api_key()

    result = run(args.logs_dir, model=model, api_key=api_key)
    print(result)

    snapshot, elapsed = tracker.snapshot()
    total_cost = sum(s["cost"] for s in snapshot.values())
    total_tokens = sum(s["input_tokens"] + s["output_tokens"] for s in snapshot.values())
    logging.getLogger(__name__).info(
        "[cost] lint finished — $%.4f total, %d tokens, %.0fs", total_cost, total_tokens, elapsed
    )
