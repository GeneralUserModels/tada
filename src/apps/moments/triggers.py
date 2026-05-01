"""Daily trigger check: re-fires logs-tada tasks whose trigger condition is now true."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model
from apps.moments.execute import _parse_frontmatter
from apps.moments.paths import get_topic, list_active_task_files
from apps.moments.state import set_pending_update

_PROMPTS = Path(__file__).parent / "prompts"
INSTRUCTION_TEMPLATE = (_PROMPTS / "triggers.txt").read_text()

_FIRED_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_fired_slugs(result: str) -> list[str]:
    """Extract the LAST fenced ```json``` block and read its `fired` list."""
    matches = _FIRED_RE.findall(result)
    if not matches:
        return []
    payload = json.loads(matches[-1])
    return list(payload.get("fired", []))


def run(
    logs_dir: str,
    model: str,
    api_key: str | None = None,
    on_round=None,
    subagent_model: str | None = None,
    subagent_api_key: str | None = None,
) -> str:
    logs_path = Path(logs_dir).resolve()
    logs_dir = str(logs_path)
    tada_dir = logs_path.parent / "logs-tada"

    triggered: list[tuple[Path, dict]] = []
    for md in list_active_task_files(tada_dir):
        fm = _parse_frontmatter(md.read_text())
        if fm.get("trigger"):
            triggered.append((md, fm))

    if not triggered:
        return "no triggered tasks"

    listing = "\n".join(
        f'- **{get_topic(md, tada_dir) or "(flat)"}/{md.stem}** — trigger: "{fm["trigger"]}"\n'
        f'  description: {fm.get("description", "")}'
        for md, fm in triggered
    )
    valid_slugs = {md.stem for md, _ in triggered}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = (
        f"Current date and time: **{now}**\n\n"
        + INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir, triggered_tasks_list=listing)
    )

    agent, _ = build_agent(
        model, logs_dir, extra_write_dirs=[str(tada_dir)], api_key=api_key,
        subagent_model=subagent_model, subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = 50
    agent.on_round = on_round
    result = agent.run([{"role": "user", "content": instruction}])

    fired_slugs = _parse_fired_slugs(result)
    fired_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    for slug in fired_slugs:
        if slug not in valid_slugs:
            continue
        set_pending_update(tada_dir, slug, reason=f"trigger fired {fired_at}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate trigger conditions on existing tada tasks")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    model = args.model or resolve_moments_model()

    result = run(args.logs_dir, model=model, api_key=resolve_moments_api_key())
    print(result)
