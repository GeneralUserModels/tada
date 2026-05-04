"""Promote discovered candidate moments into accepted markdown moments."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments.core.incremental import read_checkpoint, write_checkpoint
from apps.moments.core.candidates import (
    latest_candidate_file,
    parse_promotion_result,
    read_candidate_jsonl,
    write_accepted_moment,
)
from apps.moments.core.paths import migrate_moments_to_cadence, summarize_tada_tasks

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
PROMOTE_TEMPLATE = (_PROMPTS / "promote.txt").read_text()
PROMOTE_RULES = (_PROMPTS / "rules" / "promote.txt").read_text()
SHARED_MOMENTS = (_PROMPTS / "shared" / "moments.txt").read_text()
SHARED_USEFULNESS = (_PROMPTS / "shared" / "usefulness.txt").read_text()


def _feedback_state_summary(tada_dir: Path) -> str:
    state_path = tada_dir / "results" / "_moment_state.json"
    feedback = sorted((tada_dir / "results").glob("*/feedback_*.md")) if (tada_dir / "results").exists() else []
    parts: list[str] = []
    if state_path.exists():
        parts.append("State file exists at `results/_moment_state.json`; inspect it for negative signals and dismissed moments.")
    if feedback:
        parts.append("Recent feedback files:\n" + "\n".join(f"- {p.relative_to(tada_dir)}" for p in feedback[-20:]))
    return "\n\n".join(parts) or "- (none)"


def run(
    logs_dir: str,
    model: str,
    n: int = 8,
    api_key: str | None = None,
    on_round=None,
    subagent_model: str | None = None,
    subagent_api_key: str | None = None,
) -> str:
    logs_path = Path(logs_dir).resolve()
    tada_path = logs_path.parent / "logs-tada"
    checkpoint_path = logs_path / "moments" / ".last_promotion"
    tada_path.mkdir(parents=True, exist_ok=True)
    migrate_moments_to_cadence(tada_path)
    candidate_path = latest_candidate_file(logs_path)
    if candidate_path is None:
        return "no candidate files to promote"
    last_promotion = read_checkpoint(checkpoint_path)
    if last_promotion is not None and datetime.fromtimestamp(candidate_path.stat().st_mtime) <= last_promotion:
        return "no new candidate files to promote"
    candidates = read_candidate_jsonl(candidate_path)
    if n > 0:
        candidates = candidates[:n]

    agent, _ = build_agent(
        model, logs_dir, extra_write_dirs=[str(tada_path)], api_key=api_key,
        subagent_model=subagent_model, subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = 40
    agent.on_round = on_round

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    candidate_json = json.dumps([c.to_json() for c in candidates], indent=2)
    instruction = PROMOTE_TEMPLATE.format(
        now=now,
        promote_rules=PROMOTE_RULES,
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_path)),
        shared_usefulness=SHARED_USEFULNESS,
        accepted_moments=summarize_tada_tasks(tada_path),
        feedback_state_summary=_feedback_state_summary(tada_path),
        candidate_json=candidate_json,
    )

    result = agent.run([{"role": "user", "content": instruction}])
    promoted, _rejected = parse_promotion_result(result, candidates)
    for candidate in promoted:
        write_accepted_moment(tada_path, candidate)

    write_checkpoint(checkpoint_path)

    return f"{result}\n\nPromoted {len(promoted)} of {len(candidates)} candidates from {candidate_path}"
