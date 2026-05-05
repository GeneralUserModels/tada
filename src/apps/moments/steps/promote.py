"""Promote discovered candidate moments into accepted markdown moments."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_none

load_dotenv()

from apps.common.structured_completion import structured_completion
from apps.common.structured_ops import StructuredOpsError
from apps.moments.core.incremental import read_checkpoint, write_checkpoint
from apps.moments.core.candidates import (
    CandidateError,
    MomentCandidate,
    latest_candidate_file,
    parse_promotion_result,
    read_candidate_jsonl,
    write_accepted_moment,
)
from apps.moments.core.paths import find_task_md, get_topic, migrate_moments_to_cadence, summarize_tada_tasks
from apps.moments.schemas.structured import PromotionPayload

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
PROMOTE_TEMPLATE = (_PROMPTS / "promote.txt").read_text()
PROMOTE_RULES = (_PROMPTS / "rules" / "promote.txt").read_text()
SHARED_MOMENTS = (_PROMPTS / "shared" / "moments.txt").read_text()
SHARED_EXECUTOR_CAPABILITIES = (_PROMPTS / "shared" / "executor_capabilities.txt").read_text()
SHARED_QUALITY_BAR = (_PROMPTS / "shared" / "quality_bar.txt").read_text()
STRUCTURED_OUTPUT_ATTEMPTS = 2
logger = logging.getLogger(__name__)


def _feedback_state_summary(tada_dir: Path) -> str:
    state_path = tada_dir / "results" / "_moment_state.json"
    feedback = sorted((tada_dir / "results").glob("*/feedback_*.md")) if (tada_dir / "results").exists() else []
    parts: list[str] = []
    if state_path.exists():
        parts.append("State file exists at `results/_moment_state.json`; inspect it for negative signals and dismissed moments.")
    if feedback:
        parts.append("Recent feedback files:\n" + "\n".join(f"- {p.relative_to(tada_dir)}" for p in feedback[-20:]))
    return "\n\n".join(parts) or "- (none)"


def _route_existing_slug_updates(tada_dir: Path, candidates: list[MomentCandidate]) -> tuple[list[MomentCandidate], int]:
    routed: list[MomentCandidate] = []
    routed_count = 0
    for candidate in candidates:
        accepted_path = find_task_md(tada_dir, candidate.slug)
        if accepted_path is None:
            routed.append(candidate)
            continue
        accepted_topic = get_topic(accepted_path, tada_dir)
        if candidate.topic == accepted_topic:
            routed.append(candidate)
            continue
        routed.append(replace(candidate, topic=accepted_topic))
        routed_count += 1
    return routed, routed_count


@retry(
    stop=stop_after_attempt(STRUCTURED_OUTPUT_ATTEMPTS),
    wait=wait_none(),
    retry=retry_if_exception_type(CandidateError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _run_promotion_agent_for_valid_json(
    *,
    instruction: str,
    candidates: list[MomentCandidate],
    model: str,
    api_key: str | None,
    on_round,
):
    if on_round:
        on_round(1, 1)
    try:
        result, payload = structured_completion(
            model=model,
            instruction=instruction,
            response_model=PromotionPayload,
            api_key=api_key,
            metadata_app="moments_promote",
        )
    except StructuredOpsError as exc:
        raise CandidateError(str(exc)) from exc
    return result, parse_promotion_result(
        "```json\n" + json.dumps(payload.model_dump(exclude_none=True)) + "\n```",
        candidates,
    )


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
    candidates, routed_updates = _route_existing_slug_updates(tada_path, candidates)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    candidate_json = json.dumps([c.to_json() for c in candidates], indent=2)
    instruction = PROMOTE_TEMPLATE.format(
        now=now,
        promote_rules=PROMOTE_RULES,
        shared_executor_capabilities=SHARED_EXECUTOR_CAPABILITIES,
        shared_quality_bar=SHARED_QUALITY_BAR,
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_path)),
        accepted_moments=summarize_tada_tasks(tada_path),
        feedback_state_summary=_feedback_state_summary(tada_path),
        candidate_json=candidate_json,
    )

    result, (ranked, _rejected) = _run_promotion_agent_for_valid_json(
        instruction=instruction,
        candidates=candidates,
        model=model,
        api_key=api_key,
        on_round=on_round,
    )
    promoted = ranked[:n] if n > 0 else ranked
    for candidate in promoted:
        write_accepted_moment(tada_path, candidate)

    write_checkpoint(checkpoint_path)

    summary = f"{result}\n\nRanked {len(ranked)} of {len(candidates)} candidates. Promoted top {len(promoted)} from {candidate_path}"
    if routed_updates:
        summary += f"\nRouted {routed_updates} same-slug candidates to existing accepted moment paths."
    return summary
