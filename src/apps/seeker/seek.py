"""Analyze user activity logs to generate questions that build a richer user model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent

INSTRUCTION_TEMPLATE = (Path(__file__).parent / "prompts" / "seek.txt").read_text()


def run(logs_dir: str, model: str, api_key: str | None = None, on_round=None) -> str:
    logs_dir = str(Path(logs_dir).resolve())
    Path(logs_dir, "active-conversations").mkdir(parents=True, exist_ok=True)
    agent, _ = build_agent(model, data_dir=logs_dir, api_key=api_key)
    agent.max_rounds = 100
    agent.on_round = on_round
    instruction = INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir)
    messages = [{"role": "user", "content": instruction}]
    return agent.run(messages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze activity logs to generate user-understanding questions")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("TADA_AGENT_MODEL", "anthropic/claude-sonnet-4-6"))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
    print(result)
