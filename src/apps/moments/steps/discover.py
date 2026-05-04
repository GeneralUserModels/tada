"""Analyze user activity logs and write candidate moments as JSONL."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.common.activity_streams import (
    ActivityChunk,
    ActivityRow,
    RenderedActivityRow,
    chunk_activity_rows,
    merge_filtered_streams,
    render_activity_row,
)
from apps.common.structured_ops import StructuredOpsError, extract_json_object as extract_structured_json_object
from apps.moments.core.candidates import (
    CandidateError,
    MomentCandidate,
    validate_candidate,
    write_candidates_jsonl,
)
from apps.moments.core.incremental import read_checkpoint, write_checkpoint
from apps.moments.core.paths import migrate_moments_to_cadence, summarize_tada_tasks

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
DISCOVER_TEMPLATE = (_PROMPTS / "discover.txt").read_text()
DISCOVER_RULES = (_PROMPTS / "rules" / "discover.txt").read_text()
RECONCILE_TEMPLATE = (_PROMPTS / "reconcile.txt").read_text()
RECONCILE_RULES = (_PROMPTS / "rules" / "reconcile.txt").read_text()
SHARED_SOURCES = (_PROMPTS / "shared" / "sources.txt").read_text()
SHARED_MOMENTS = (_PROMPTS / "shared" / "moments.txt").read_text()
SHARED_USEFULNESS = (_PROMPTS / "shared" / "usefulness.txt").read_text()

FILTERED_STREAM_SOURCES = [
    "screen/filtered.jsonl",
    "email/filtered.jsonl",
    "calendar/filtered.jsonl",
    "notifications/filtered.jsonl",
    "filesys/filtered.jsonl",
]
CHUNK_TARGET_CHARS = 50_000
CHUNK_OVERLAP_CHARS = 7_500
VALUE_MAX_CHARS = 700
DRAFT_CATALOG_MAX_CHARS = 8_000
DRAFT_DETAILS_MAX_COUNT = 8

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


def _merged_filtered_rows(logs_path: Path, since: datetime | None):
    return merge_filtered_streams(logs_path, since, FILTERED_STREAM_SOURCES)


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


def _draft_context(drafts: dict[str, MomentCandidate], chunk: ActivityChunk) -> str:
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

    chunk_tokens = _tokenize(chunk.rendered_text)
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


def _lookup_draft(drafts: dict[str, MomentCandidate], key: Any, field: str = "id") -> MomentCandidate:
    if not isinstance(key, str) or not key.strip():
        raise CandidateError(f"{field} is required")
    normalized = key.strip()
    for candidate in drafts.values():
        if normalized in (candidate.id, candidate.slug):
            return candidate
    raise CandidateError(f"unknown draft id or slug: {normalized}")


def _operation_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise CandidateError(f"discovery patch JSON {field} must be a list")
    return value


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        return extract_structured_json_object(text)
    except StructuredOpsError as exc:
        raise CandidateError(str(exc)) from exc


def _parse_draft_patch_result(result: str) -> tuple[dict[str, Any], str]:
    payload = _extract_json_object(result)
    patch = {
        "create": _operation_list(payload, "create"),
        "update": _operation_list(payload, "update"),
        "merge": _operation_list(payload, "merge"),
        "reject": _operation_list(payload, "reject"),
    }
    notes = payload.get("notes", "")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise CandidateError("discovery patch JSON notes must be a string")
    return patch, notes.strip()


def _apply_draft_patch(drafts: dict[str, MomentCandidate], patch: dict[str, Any]) -> list[dict[str, str]]:
    rejected: list[dict[str, str]] = []

    for raw in patch.get("create", []):
        candidate = validate_candidate(raw)
        for existing in drafts.values():
            if candidate.id == existing.id or candidate.slug == existing.slug:
                raise CandidateError(f"duplicate created draft id or slug: {candidate.id}")
        drafts[candidate.id] = candidate

    for raw in patch.get("update", []):
        if not isinstance(raw, dict):
            raise CandidateError("update entries must be objects")
        candidate = _lookup_draft(drafts, raw.get("id") or raw.get("slug"), "update.id")
        fields = raw.get("fields")
        if not isinstance(fields, dict):
            raise CandidateError("update entries require fields object")
        current = candidate.to_json()
        allowed = set(current)
        for key, value in fields.items():
            if key not in allowed:
                raise CandidateError(f"unknown update field: {key}")
            current[key] = value
        updated = validate_candidate(current)
        for existing_id, existing in drafts.items():
            if existing_id == candidate.id:
                continue
            if updated.id == existing.id or updated.slug == existing.slug:
                raise CandidateError(f"update creates duplicate draft id or slug: {updated.id}")
        drafts.pop(candidate.id)
        drafts[updated.id] = updated

    for raw in patch.get("merge", []):
        if not isinstance(raw, dict):
            raise CandidateError("merge entries must be objects")
        from_candidate = _lookup_draft(drafts, raw.get("from"), "merge.from")
        into_candidate = _lookup_draft(drafts, raw.get("into"), "merge.into")
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise CandidateError("merge entries require reason")
        if from_candidate.id == into_candidate.id:
            raise CandidateError("merge.from and merge.into must be different")
        drafts.pop(from_candidate.id)
        rejected.append({"id": from_candidate.id, "reason": reason.strip()})

    for raw in patch.get("reject", []):
        if not isinstance(raw, dict):
            raise CandidateError("reject entries must be objects")
        candidate = _lookup_draft(drafts, raw.get("id") or raw.get("slug"), "reject.id")
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise CandidateError("reject entries require reason")
        drafts.pop(candidate.id)
        rejected.append({"id": candidate.id, "reason": reason.strip()})

    return rejected


def _parse_reconcile_result(result: str) -> tuple[list[MomentCandidate], list[dict[str, str]], list[dict[str, str]], str]:
    payload = _extract_json_object(result)
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


def _build_instruction(
    *,
    now: str,
    mode: str,
    last_discovery: datetime | None,
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
        logs_dir=logs_dir,
        tada_dir=str(tada_dir),
        discover_rules=DISCOVER_RULES,
        shared_sources=SHARED_SOURCES.format(logs_dir=logs_dir),
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_dir)),
        shared_usefulness=SHARED_USEFULNESS,
        accepted_moments=accepted_moments,
        feedback_state_summary=feedback_state_summary,
        chunk_metadata=chunk.metadata,
        activity_chunk=chunk.rendered_text,
        draft_context=draft_context,
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
        shared_moments=SHARED_MOMENTS.format(tada_dir=str(tada_dir)),
        shared_usefulness=SHARED_USEFULNESS,
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
    agent, _ = build_agent(
        model,
        logs_dir,
        extra_write_dirs=[str(logs_path / "moments")],
        api_key=api_key,
        subagent_model=subagent_model,
        subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = 30
    agent.on_round = on_round
    result = agent.run([{"role": "user", "content": instruction}])
    return _parse_reconcile_result(result)


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

    last_discovery = read_checkpoint(checkpoint_path)
    mode = "first_run" if last_discovery is None else "incremental"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    accepted_moments = summarize_tada_tasks(tada_dir)
    feedback_summary = _feedback_state_summary(tada_dir)

    drafts: dict[str, MomentCandidate] = {}
    rejected: list[dict[str, str]] = []
    notes: list[str] = []
    chunks_processed = 0

    rows = _merged_filtered_rows(logs_path, last_discovery)
    chunks = _chunk_filtered_rows(rows)
    for chunk in chunks:
        chunks_processed += 1
        instruction = _build_instruction(
            now=now,
            mode=mode,
            last_discovery=last_discovery,
            logs_dir=logs_dir,
            tada_dir=tada_dir,
            accepted_moments=accepted_moments,
            feedback_state_summary=feedback_summary,
            chunk=chunk,
            draft_context=_draft_context(drafts, chunk),
        )
        agent, _ = build_agent(
            model,
            logs_dir,
            extra_write_dirs=[str(logs_path / "moments")],
            api_key=api_key,
            subagent_model=subagent_model,
            subagent_api_key=subagent_api_key,
        )
        agent.max_rounds = 80
        agent.on_round = on_round
        result = agent.run([{"role": "user", "content": instruction}])
        patch, chunk_notes = _parse_draft_patch_result(result)
        rejected.extend(_apply_draft_patch(drafts, patch))
        if chunk_notes:
            notes.append(f"chunk {chunk.index}: {chunk_notes}")

    if chunks_processed == 0:
        mode = "no_new_data"

    candidates, reconcile_rejected, updates, reconcile_notes = _reconcile_drafts(
        drafts=list(drafts.values()),
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
        f"Processed {chunks_processed} discovery chunks.",
        f"Reconciled {len(drafts)} drafts to {len(candidates)} candidates.",
        f"Wrote {len(candidates)} candidates to {candidate_path}",
    ]
    if rejected:
        summary.append(f"Rejected or merged {len(rejected)} drafts during discovery.")
    if updates:
        summary.append(f"Routed {len(updates)} candidates as updates to accepted moments.")
    if notes:
        summary.append("Notes:\n" + "\n".join(f"- {note}" for note in notes[-10:]))
    return "\n".join(summary)
