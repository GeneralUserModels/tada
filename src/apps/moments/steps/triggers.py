"""Daily trigger check: re-fires logs-tada tasks whose trigger condition is now true."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

from agent.builder import build_agent
from apps.common.structured_ops import StructuredOpsError, extract_json_object
from apps.moments.runtime.execute import _parse_frontmatter
from apps.moments.core.paths import get_topic, list_active_task_files, migrate_moments_to_cadence
from apps.moments.core.state import set_pending_update
from apps.moments.schemas.structured import TriggerPayload

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
INSTRUCTION_TEMPLATE = (_PROMPTS / "triggers.txt").read_text()
TRIGGER_RULES = (_PROMPTS / "rules" / "triggers.txt").read_text()
SHARED_SOURCES = (_PROMPTS / "shared" / "sources.txt").read_text()


def _parse_fired_slugs(result: str) -> list[str]:
    """Extract and validate the agent's `fired` slug list."""
    try:
        payload = TriggerPayload.model_validate(extract_json_object(result))
    except (StructuredOpsError, ValidationError):
        return []
    return payload.fired


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
    migrate_moments_to_cadence(tada_dir)

    triggered: list[tuple[Path, dict]] = []
    for md in list_active_task_files(tada_dir):
        fm = _parse_frontmatter(md.read_text())
        if fm.get("cadence") == "trigger" and fm.get("trigger"):
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
        INSTRUCTION_TEMPLATE.format(
            now=now,
            logs_dir=logs_dir,
            triggered_tasks_list=listing,
            trigger_rules=TRIGGER_RULES,
            shared_sources=SHARED_SOURCES.format(logs_dir=logs_dir),
        )
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
