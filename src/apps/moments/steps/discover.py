"""Analyze user activity logs and write candidate moments as JSONL."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic import ValidationError
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_none

load_dotenv()

from apps.common.activity_streams import (
    ActivityChunk,
    ActivityRow,
    RenderedActivityRow,
    chunk_activity_rows,
    merge_filtered_streams,
    parse_timestamp,
    render_activity_row,
)
from apps.common.structured_completion import structured_completion
from apps.common.structured_ops import StructuredOpsError, extract_json_object
from agent.builder import build_agent, _ensure_sandbox
from apps.moments.core.candidates import (
    CandidateError,
    MomentCandidate,
    validate_candidate,
    write_candidates_jsonl,
)
from apps.moments.core.incremental import read_checkpoint, write_checkpoint
from apps.moments.core.paths import migrate_moments_to_cadence, summarize_tada_tasks
from apps.moments.schemas.structured import DraftActionPayload, IdeaPayload, ReconcilePayload

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
DISCOVER_TEMPLATE = (_PROMPTS / "discover.txt").read_text()
DISCOVER_COMPILE_TEMPLATE = (_PROMPTS / "discover_compile.txt").read_text()
DISCOVER_RULES = (_PROMPTS / "rules" / "discover.txt").read_text()
RECONCILE_TEMPLATE = (_PROMPTS / "reconcile.txt").read_text()
RECONCILE_RULES = (_PROMPTS / "rules" / "reconcile.txt").read_text()
SHARED_SOURCES = (_PROMPTS / "shared" / "sources.txt").read_text()
SHARED_MOMENTS = (_PROMPTS / "shared" / "moments.txt").read_text()
SHARED_EXECUTOR_CAPABILITIES = (_PROMPTS / "shared" / "executor_capabilities.txt").read_text()
SHARED_QUALITY_BAR = (_PROMPTS / "shared" / "quality_bar.txt").read_text()

FILTERED_STREAM_SOURCES = [
    "screen/filtered.jsonl",
    "email/filtered.jsonl",
    "calendar/filtered.jsonl",
    "notifications/filtered.jsonl",
    "filesys/filtered.jsonl",
]
ESTIMATED_CHARS_PER_TOKEN = 4
CHUNK_TARGET_TOKENS = 64_000
CHUNK_OVERLAP_TOKENS = 8_000
CHUNK_TARGET_CHARS = CHUNK_TARGET_TOKENS * ESTIMATED_CHARS_PER_TOKEN
CHUNK_OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * ESTIMATED_CHARS_PER_TOKEN
DISCOVERY_CHUNK_CONCURRENCY = 4
INITIAL_DISCOVERY_LOOKBACK = timedelta(days=1)
VALUE_MAX_CHARS = 700
DRAFT_CATALOG_MAX_CHARS = 8_000
DRAFT_DETAILS_MAX_COUNT = 8
STRUCTURED_OUTPUT_ATTEMPTS = 2
AGENT_IDEATION_MAX_ROUNDS = 30
logger = logging.getLogger(__name__)
_BUILD_AGENT_LOCK = Lock()

_TOKEN_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "from",
    "into",
    "that",
    "their",
    "there",
    "this",
    "through",
    "with",
    "without",
}

FilteredRow = ActivityRow
RenderedRow = RenderedActivityRow


@dataclass(frozen=True)
class ChunkDiscoveryResult:
    chunk_index: int
    upserts: list[MomentCandidate]
    rejected: list[dict[str, str]]
    removed: list[dict[str, str]]
    idea_notes: str
    compiler_notes: str


def _merged_filtered_rows(logs_path: Path, since: datetime | None):
    return merge_filtered_streams(logs_path, since, FILTERED_STREAM_SOURCES)


def _iter_jsonl_lines_reverse(path: Path, block_size: int = 8192):
    with path.open("rb") as f:
        f.seek(0, 2)
        position = f.tell()
        buffer = b""
        while position > 0:
            read_size = min(block_size, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)
            lines = (chunk + buffer).splitlines()
            if position > 0:
                buffer = lines[0] if lines else chunk + buffer
                lines = lines[1:]
            else:
                buffer = b""
            for line in reversed(lines):
                yield line.decode(errors="replace")
        if buffer:
            yield buffer.decode(errors="replace")


def _latest_timestamp_in_jsonl(path: Path) -> datetime | None:
    if not path.exists() or not path.is_file():
        return None
    for line in _iter_jsonl_lines_reverse(path):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        parsed = parse_timestamp(entry.get("timestamp"))
        if parsed is not None:
            return parsed[0]
    return None


def _initial_discovery_since(logs_path: Path) -> datetime:
    latest = None
    for rel_path in FILTERED_STREAM_SOURCES:
        ts = _latest_timestamp_in_jsonl(logs_path / rel_path)
        if ts is not None and (latest is None or ts > latest):
            latest = ts
    return (latest or datetime.now()) - INITIAL_DISCOVERY_LOOKBACK


def _render_filtered_row(row: FilteredRow) -> str:
    return render_activity_row(row, max_chars=VALUE_MAX_CHARS)


def _chunk_filtered_rows(
    rows: Iterator[FilteredRow],
    target_chars: int | None = None,
    overlap_chars: int | None = None,
) -> Iterator[ActivityChunk]:
    target_chars = CHUNK_TARGET_CHARS if target_chars is None else target_chars
    overlap_chars = CHUNK_OVERLAP_CHARS if overlap_chars is None else overlap_chars
    yield from chunk_activity_rows(rows, target_chars=target_chars, overlap_chars=overlap_chars)


def _feedback_state_summary(tada_dir: Path) -> str:
    state_path = tada_dir / "results" / "_moment_state.json"
    feedback = sorted((tada_dir / "results").glob("*/feedback_*.md")) if (tada_dir / "results").exists() else []
    parts: list[str] = []
    if state_path.exists():
        parts.append("State file exists at `results/_moment_state.json`; inspect it for dismissals, pins, thumbs, and pending updates.")
    if feedback:
        parts.append("Feedback files:\n" + "\n".join(f"- {p.relative_to(tada_dir)}" for p in feedback[-20:]))
    return "\n\n".join(parts) or "- (none)"


def _candidate_json(candidates: list[MomentCandidate]) -> str:
    return json.dumps([candidate.to_json() for candidate in candidates], indent=2, sort_keys=True)


def _tokenize(text: str) -> set[str]:
    import re

    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{3,}", text.lower())
        if token not in _TOKEN_STOPWORDS
    }


def _candidate_search_text(candidate: MomentCandidate) -> str:
    return " ".join(
        [
            candidate.id,
            candidate.slug,
            candidate.topic,
            candidate.title,
            candidate.description,
            candidate.specific_instructions,
            candidate.desired_artifact,
            " ".join(candidate.evidence),
            " ".join(candidate.source_paths),
            candidate.why_now,
            candidate.user_value,
        ]
    )


def _draft_context_for_text(drafts: dict[str, MomentCandidate], text: str) -> str:
    if not drafts:
        return "## Draft Catalog\n\n(no drafts yet)\n\n## Relevant Draft Details\n\n[]"

    ordered = sorted(drafts.values(), key=lambda c: (c.topic, c.slug))
    lines: list[str] = []
    used_chars = 0
    omitted = 0
    for candidate in ordered:
        line = (
            f"- `{candidate.id}` / `{candidate.slug}` [{candidate.topic}, {candidate.cadence}] "
            f"{candidate.title}: {candidate.description} "
            f"(evidence={len(candidate.evidence)}, usefulness={candidate.usefulness}, confidence={candidate.confidence:.2f})"
        )
        if used_chars + len(line) + 1 > DRAFT_CATALOG_MAX_CHARS:
            omitted += 1
            continue
        lines.append(line)
        used_chars += len(line) + 1

    chunk_tokens = _tokenize(text)
    scored: list[tuple[int, str, MomentCandidate]] = []
    for candidate in ordered:
        score = len(chunk_tokens & _tokenize(_candidate_search_text(candidate)))
        if score > 0:
            scored.append((score, candidate.id, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    relevant = [candidate.to_json() for _, _, candidate in scored[:DRAFT_DETAILS_MAX_COUNT]]

    catalog = "\n".join(lines) if lines else "(catalog omitted due budget)"
    if omitted:
        catalog += f"\n- ... {omitted} additional drafts omitted from compact catalog due budget"
    return (
        "## Draft Catalog\n\n"
        f"{catalog}\n\n"
        "## Relevant Draft Details\n\n"
        "```json\n"
        f"{json.dumps(relevant, indent=2, sort_keys=True)}\n"
        "```"
    )


def _validate_rejected(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CandidateError("discovery draft JSON rejected must be a list")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise CandidateError("discovery draft JSON rejected entries must be objects")
        key = item.get("id") or item.get("slug")
        reason = item.get("reason")
        if not isinstance(key, str) or not key.strip():
            raise CandidateError("discovery draft JSON rejected entries require id")
        if not isinstance(reason, str) or not reason.strip():
            raise CandidateError("discovery draft JSON rejected entries require reason")
        result.append({"id": key.strip(), "reason": reason.strip()})
    return result


def _parse_structured_ideas(payload: IdeaPayload) -> tuple[list[dict[str, Any]], str]:
    data = payload.model_dump(exclude_none=True)
    ideas = data.get("ideas", [])
    if not isinstance(ideas, list):
        raise CandidateError("idea JSON ideas must be a list")
    notes = data.get("notes", "")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise CandidateError("idea JSON notes must be a string")
    return ideas, notes.strip()


def _parse_draft_action_payload(payload: dict[str, Any]) -> tuple[list[MomentCandidate], list[dict[str, str]], list[dict[str, str]], str]:
    raw_candidates = payload.get("upserts", [])
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        raise CandidateError("draft action JSON upserts must be a list")
    upserts = [validate_candidate(raw) for raw in raw_candidates]
    seen: set[str] = set()
    for candidate in upserts:
        if candidate.id in seen or candidate.slug in seen:
            raise CandidateError(f"duplicate draft action candidate id or slug: {candidate.id}")
        seen.add(candidate.id)
        seen.add(candidate.slug)

    notes = payload.get("notes", "")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise CandidateError("draft action JSON notes must be a string")
    return upserts, _validate_rejected(payload.get("rejected", [])), _validate_rejected(payload.get("remove", [])), notes.strip()


def _parse_structured_draft_actions(payload: DraftActionPayload) -> tuple[list[MomentCandidate], list[dict[str, str]], list[dict[str, str]], str]:
    return _parse_draft_action_payload(payload.model_dump(exclude_none=True))


def _parse_reconcile_payload(payload: dict[str, Any]) -> tuple[list[MomentCandidate], list[dict[str, str]], list[dict[str, str]], str]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise CandidateError("reconciliation JSON must contain candidates list")
    candidates = [validate_candidate(raw) for raw in raw_candidates]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.id in seen or candidate.slug in seen:
            raise CandidateError(f"duplicate reconciled candidate id or slug: {candidate.id}")
        seen.add(candidate.id)
        seen.add(candidate.slug)

    updates_raw = payload.get("updates", [])
    if not isinstance(updates_raw, list):
        raise CandidateError("reconciliation JSON updates must be a list")
    updates: list[dict[str, str]] = []
    for item in updates_raw:
        if not isinstance(item, dict):
            raise CandidateError("reconciliation JSON updates entries must be objects")
        candidate_id = item.get("candidate_id") or item.get("id") or item.get("slug")
        accepted_slug = item.get("accepted_slug") or item.get("target_slug")
        reason = item.get("reason")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise CandidateError("reconciliation updates entries require candidate_id")
        if not isinstance(accepted_slug, str) or not accepted_slug.strip():
            raise CandidateError("reconciliation updates entries require accepted_slug")
        if not isinstance(reason, str) or not reason.strip():
            raise CandidateError("reconciliation updates entries require reason")
        updates.append({
            "candidate_id": candidate_id.strip(),
            "accepted_slug": accepted_slug.strip(),
            "reason": reason.strip(),
        })

    notes = payload.get("notes", "")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise CandidateError("reconciliation JSON notes must be a string")
    return candidates, _validate_rejected(payload.get("rejected", [])), updates, notes.strip()


def _parse_structured_reconcile(payload: ReconcilePayload) -> tuple[list[MomentCandidate], list[dict[str, str]], list[dict[str, str]], str]:
    return _parse_reconcile_payload(payload.model_dump(exclude_none=True))


def _run_tool_agent_for_ideation(
    *,
    instruction: str,
    logs_dir: str,
    model: str,
    api_key: str | None,
    on_round,
    subagent_model: str | None,
    subagent_api_key: str | None,
) -> str:
    with _BUILD_AGENT_LOCK:
        agent, _ = build_agent(
            model,
            logs_dir,
            api_key=api_key,
            subagent_model=subagent_model,
            subagent_api_key=subagent_api_key,
        )
    agent.max_rounds = AGENT_IDEATION_MAX_ROUNDS
    agent.on_round = on_round
    result = agent.run(
        [{"role": "user", "content": instruction}],
        final_response_model=IdeaPayload,
        final_instruction=(
            "Convert your discovery work into the required structured idea payload. "
            "Return only ideas that are explicitly supported by the activity context or tool results. "
            "If there are no grounded ideas, return an empty ideas list and explain why in notes."
        ),
        final_metadata_app="moments_ideation",
    ).strip()
    if not result or result == "(max rounds reached)":
        raise CandidateError("discovery ideation agent did not produce usable notes")
    return result


def _parse_agent_ideas(result: str) -> tuple[list[dict[str, Any]], str]:
    try:
        try:
            payload = extract_json_object(result)
            parsed = IdeaPayload.model_validate(payload)
        except StructuredOpsError:
            parsed = IdeaPayload.model_validate_json(result)
    except (StructuredOpsError, ValidationError) as exc:
        raise CandidateError(f"discovery ideation agent returned invalid idea JSON: {exc}") from exc
    return _parse_structured_ideas(parsed)


@retry(
    stop=stop_after_attempt(STRUCTURED_OUTPUT_ATTEMPTS),
    wait=wait_none(),
    retry=retry_if_exception_type(CandidateError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _run_agent_for_valid_json(
    *,
    instruction: str,
    model: str,
    api_key: str | None,
    on_round,
    response_model: type[BaseModel],
    metadata_app: str,
    parser,
):
    if on_round:
        on_round(1, 1)
    try:
        result, payload = structured_completion(
            model=model,
            instruction=instruction,
            response_model=response_model,
            api_key=api_key,
            metadata_app=metadata_app,
        )
        parsed = parser(payload)
    except StructuredOpsError as exc:
        raise CandidateError(str(exc)) from exc
    return result, parsed


def _build_instruction(
    *,
    now: str,
    mode: str,
    last_discovery: datetime | None,
    activity_since: datetime | None,
    logs_dir: str,
    tada_dir: Path,
    accepted_moments: str,
    feedback_state_summary: str,
    chunk: ActivityChunk,
    draft_context: str,
) -> str:
    return DISCOVER_TEMPLATE.format(
        now=now,
        mode=mode,
        last_discovery_date=last_discovery.strftime("%Y-%m-%d %H:%M") if last_discovery else "never",
        activity_since_date=activity_since.strftime("%Y-%m-%d %H:%M") if activity_since else "beginning",
        logs_dir=logs_dir,
        tada_dir=str(tada_dir),
        discover_rules=DISCOVER_RULES,
        shared_executor_capabilities=SHARED_EXECUTOR_CAPABILITIES,
        shared_quality_bar=SHARED_QUALITY_BAR,
        shared_sources=SHARED_SOURCES.format(logs_dir=logs_dir),
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_dir)),
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        chunk_metadata=chunk.metadata,
        activity_chunk=chunk.rendered_text,
        draft_context=draft_context,
    )


def _build_draft_action_instruction(
    *,
    now: str,
    logs_dir: str,
    tada_dir: Path,
    accepted_moments: str,
    feedback_state_summary: str,
    ideas: list[dict[str, Any]],
) -> str:
    return DISCOVER_COMPILE_TEMPLATE.format(
        now=now,
        logs_dir=logs_dir,
        tada_dir=str(tada_dir),
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_dir)),
        shared_executor_capabilities=SHARED_EXECUTOR_CAPABILITIES,
        shared_quality_bar=SHARED_QUALITY_BAR,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        idea_json=json.dumps(ideas, indent=2, sort_keys=True),
    )


def _build_reconcile_instruction(
    *,
    now: str,
    logs_dir: str,
    tada_dir: Path,
    accepted_moments: str,
    feedback_state_summary: str,
    draft_candidates: list[MomentCandidate],
) -> str:
    return RECONCILE_TEMPLATE.format(
        now=now,
        logs_dir=logs_dir,
        tada_dir=str(tada_dir),
        reconcile_rules=RECONCILE_RULES,
        shared_quality_bar=SHARED_QUALITY_BAR,
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_dir)),
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        draft_candidate_json=_candidate_json(draft_candidates),
    )


def _reconcile_drafts(
    *,
    drafts: list[MomentCandidate],
    now: str,
    logs_dir: str,
    logs_path: Path,
    tada_dir: Path,
    accepted_moments: str,
    feedback_state_summary: str,
    model: str,
    api_key: str | None,
    on_round,
    subagent_model: str | None,
    subagent_api_key: str | None,
) -> tuple[list[MomentCandidate], list[dict[str, str]], list[dict[str, str]], str]:
    if not drafts:
        return [], [], [], ""
    instruction = _build_reconcile_instruction(
        now=now,
        logs_dir=logs_dir,
        tada_dir=tada_dir,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        draft_candidates=drafts,
    )
    _result, parsed = _run_agent_for_valid_json(
        instruction=instruction,
        model=model,
        api_key=api_key,
        on_round=on_round,
        response_model=ReconcilePayload,
        metadata_app="moments_reconcile",
        parser=_parse_structured_reconcile,
    )
    return parsed


def _process_discovery_chunk(
    *,
    chunk: ActivityChunk,
    now: str,
    mode: str,
    last_discovery: datetime | None,
    activity_since: datetime | None,
    logs_dir: str,
    tada_dir: Path,
    accepted_moments: str,
    feedback_state_summary: str,
    model: str,
    api_key: str | None,
    on_round,
    subagent_model: str | None,
    subagent_api_key: str | None,
) -> ChunkDiscoveryResult:
    instruction = _build_instruction(
        now=now,
        mode=mode,
        last_discovery=last_discovery,
        activity_since=activity_since,
        logs_dir=logs_dir,
        tada_dir=tada_dir,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        chunk=chunk,
        draft_context=_draft_context_for_text({}, chunk.rendered_text),
    )
    agent_result = _run_tool_agent_for_ideation(
        instruction=instruction,
        logs_dir=logs_dir,
        model=model,
        api_key=api_key,
        on_round=on_round,
        subagent_model=subagent_model,
        subagent_api_key=subagent_api_key,
    )
    ideas, idea_notes = _parse_agent_ideas(agent_result)
    compiler_instruction = _build_draft_action_instruction(
        now=now,
        logs_dir=logs_dir,
        tada_dir=tada_dir,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        ideas=ideas,
    )
    _result, (upserts, chunk_rejected, removed_drafts, compiler_notes) = _run_agent_for_valid_json(
        instruction=compiler_instruction,
        model=model,
        api_key=api_key,
        on_round=on_round,
        response_model=DraftActionPayload,
        metadata_app="moments_draft_compile",
        parser=_parse_structured_draft_actions,
    )
    return ChunkDiscoveryResult(
        chunk_index=chunk.index,
        upserts=upserts,
        rejected=chunk_rejected,
        removed=removed_drafts,
        idea_notes=idea_notes,
        compiler_notes=compiler_notes,
    )


def _process_discovery_chunks(
    *,
    chunks: list[ActivityChunk],
    now: str,
    mode: str,
    last_discovery: datetime | None,
    activity_since: datetime | None,
    logs_dir: str,
    tada_dir: Path,
    accepted_moments: str,
    feedback_state_summary: str,
    model: str,
    api_key: str | None,
    on_round,
    subagent_model: str | None,
    subagent_api_key: str | None,
) -> list[ChunkDiscoveryResult]:
    if not chunks:
        return []
    max_workers = max(1, min(DISCOVERY_CHUNK_CONCURRENCY, len(chunks)))
    if max_workers == 1:
        return [
            _process_discovery_chunk(
                chunk=chunk,
                now=now,
                mode=mode,
                last_discovery=last_discovery,
                activity_since=activity_since,
                logs_dir=logs_dir,
                tada_dir=tada_dir,
                accepted_moments=accepted_moments,
                feedback_state_summary=feedback_state_summary,
                model=model,
                api_key=api_key,
                on_round=on_round,
                subagent_model=subagent_model,
                subagent_api_key=subagent_api_key,
            )
            for chunk in chunks
        ]

    results: list[ChunkDiscoveryResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                _process_discovery_chunk,
                chunk=chunk,
                now=now,
                mode=mode,
                last_discovery=last_discovery,
                activity_since=activity_since,
                logs_dir=logs_dir,
                tada_dir=tada_dir,
                accepted_moments=accepted_moments,
                feedback_state_summary=feedback_state_summary,
                model=model,
                api_key=api_key,
                on_round=on_round,
                subagent_model=subagent_model,
                subagent_api_key=subagent_api_key,
            )
            for chunk in chunks
        ]
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda result: result.chunk_index)


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
    checkpoint_path = logs_path / "moments" / ".last_discovery"
    tada_dir = logs_path.parent / "logs-tada"
    (logs_path / "moments").mkdir(parents=True, exist_ok=True)
    tada_dir.mkdir(parents=True, exist_ok=True)
    migrate_moments_to_cadence(tada_dir)
    _ensure_sandbox([logs_dir])

    last_discovery = read_checkpoint(checkpoint_path)
    mode = "first_run" if last_discovery is None else "incremental"
    activity_since = last_discovery if last_discovery is not None else _initial_discovery_since(logs_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    accepted_moments = summarize_tada_tasks(tada_dir)
    feedback_summary = _feedback_state_summary(tada_dir)

    draft_candidates: list[MomentCandidate] = []
    rejected: list[dict[str, str]] = []
    notes: list[str] = []

    rows = _merged_filtered_rows(logs_path, activity_since)
    chunks = list(_chunk_filtered_rows(rows))
    chunks_processed = len(chunks)
    chunk_results = _process_discovery_chunks(
        chunks=chunks,
        now=now,
        mode=mode,
        last_discovery=last_discovery,
        activity_since=activity_since,
        logs_dir=logs_dir,
        tada_dir=tada_dir,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_summary,
        model=model,
        api_key=api_key,
        on_round=on_round,
        subagent_model=subagent_model,
        subagent_api_key=subagent_api_key,
    )
    for chunk_result in chunk_results:
        draft_candidates.extend(chunk_result.upserts)
        rejected.extend(chunk_result.rejected)
        rejected.extend(chunk_result.removed)
        chunk_note_parts = []
        if chunk_result.idea_notes:
            chunk_note_parts.append(f"ideas: {chunk_result.idea_notes}")
        if chunk_result.compiler_notes:
            chunk_note_parts.append(f"compiled: {chunk_result.compiler_notes}")
        if chunk_result.removed:
            chunk_note_parts.append(f"ignored {len(chunk_result.removed)} remove ops from parallel chunk compile")
        if chunk_note_parts:
            notes.append(f"chunk {chunk_result.chunk_index}: " + " | ".join(chunk_note_parts))

    if chunks_processed == 0:
        mode = "no_new_data"

    candidates, reconcile_rejected, updates, reconcile_notes = _reconcile_drafts(
        drafts=draft_candidates,
        now=now,
        logs_dir=logs_dir,
        logs_path=logs_path,
        tada_dir=tada_dir,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_summary,
        model=model,
        api_key=api_key,
        on_round=on_round,
        subagent_model=subagent_model,
        subagent_api_key=subagent_api_key,
    )
    rejected.extend(reconcile_rejected)
    if reconcile_notes:
        notes.append(f"reconciliation: {reconcile_notes}")

    candidate_path = write_candidates_jsonl(logs_path, candidates)
    write_checkpoint(checkpoint_path)
    summary = [
        f"Mode: {mode}",
        f"Activity window starts after: {activity_since.strftime('%Y-%m-%d %H:%M')}",
        f"Processed {chunks_processed} discovery chunks.",
        f"Reconciled {len(draft_candidates)} drafts to {len(candidates)} candidates.",
        f"Wrote {len(candidates)} candidates to {candidate_path}",
    ]
    if rejected:
        summary.append(f"Rejected or merged {len(rejected)} drafts during discovery.")
    if updates:
        summary.append(f"Routed {len(updates)} candidates as updates to accepted moments.")
    if notes:
        summary.append("Notes:\n" + "\n".join(f"- {note}" for note in notes[-10:]))
    return "\n".join(summary)
