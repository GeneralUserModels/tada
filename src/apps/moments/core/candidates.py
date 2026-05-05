"""Deterministic helpers for moments candidate JSON and accepted markdown."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
VALID_CADENCES = {"once", "scheduled", "trigger"}


class CandidateError(ValueError):
    """Raised when model-provided candidate or promotion JSON is invalid."""


@dataclass(frozen=True)
class MomentCandidate:
    id: str
    slug: str
    topic: str
    title: str
    description: str
    cadence: str
    schedule: str
    trigger: str
    confidence: float
    usefulness: int
    specific_instructions: str
    desired_artifact: str
    evidence: list[str]
    source_paths: list[str]
    why_now: str
    user_value: str

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "topic": self.topic,
            "title": self.title,
            "description": self.description,
            "cadence": self.cadence,
            "schedule": self.schedule,
            "trigger": self.trigger,
            "confidence": self.confidence,
            "usefulness": self.usefulness,
            "specific_instructions": self.specific_instructions,
            "desired_artifact": self.desired_artifact,
            "evidence": self.evidence,
            "source_paths": self.source_paths,
            "why_now": self.why_now,
            "user_value": self.user_value,
        }


def slugify(value: str, fallback: str = "moment") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug or fallback


def extract_json_object(text: str) -> dict[str, Any]:
    matches = JSON_BLOCK_RE.findall(text)
    if not matches:
        raise CandidateError("missing fenced JSON block")
    try:
        payload = json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise CandidateError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CandidateError("JSON payload must be an object")
    return payload


def _string(value: Any, field: str, required: bool = True) -> str:
    if value is None:
        if required:
            raise CandidateError(f"{field} is required")
        return ""
    if not isinstance(value, str):
        raise CandidateError(f"{field} must be a string")
    text = value.strip()
    if required and not text:
        raise CandidateError(f"{field} is required")
    return text


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CandidateError(f"{field} must be a list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise CandidateError(f"{field} items must be strings")
        text = item.strip()
        if text:
            result.append(text)
    return result


def validate_candidate(raw: dict[str, Any]) -> MomentCandidate:
    if not isinstance(raw, dict):
        raise CandidateError("candidate must be an object")
    title = _string(raw.get("title"), "title")
    slug = slugify(_string(raw.get("slug"), "slug", required=False) or title)
    topic = slugify(_string(raw.get("topic"), "topic", required=False) or "general", fallback="general")
    candidate_id = slugify(_string(raw.get("id"), "id", required=False) or slug)
    cadence = _string(raw.get("cadence"), "cadence")
    if cadence not in VALID_CADENCES:
        raise CandidateError(f"cadence must be one of {sorted(VALID_CADENCES)}")
    schedule = _string(raw.get("schedule"), "schedule", required=False)
    trigger = _string(raw.get("trigger"), "trigger", required=False)
    if cadence == "scheduled" and not schedule:
        raise CandidateError("scheduled candidates require schedule")
    if cadence == "trigger" and not trigger:
        raise CandidateError("trigger candidates require trigger")
    if cadence != "scheduled":
        schedule = ""
    if cadence != "trigger":
        trigger = ""
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise CandidateError("confidence must be a number") from exc
    if not 0 <= confidence <= 1:
        raise CandidateError("confidence must be between 0 and 1")
    try:
        usefulness = int(raw.get("usefulness"))
    except (TypeError, ValueError) as exc:
        raise CandidateError("usefulness must be an integer") from exc
    if not 1 <= usefulness <= 10:
        raise CandidateError("usefulness must be between 1 and 10")
    return MomentCandidate(
        id=candidate_id,
        slug=slug,
        topic=topic,
        title=title,
        description=_string(raw.get("description"), "description"),
        cadence=cadence,
        schedule=schedule,
        trigger=trigger,
        confidence=confidence,
        usefulness=usefulness,
        specific_instructions=_string(raw.get("specific_instructions"), "specific_instructions"),
        desired_artifact=_string(raw.get("desired_artifact"), "desired_artifact"),
        evidence=_string_list(raw.get("evidence"), "evidence"),
        source_paths=_string_list(raw.get("source_paths"), "source_paths"),
        why_now=_string(raw.get("why_now"), "why_now"),
        user_value=_string(raw.get("user_value"), "user_value"),
    )


def parse_discovery_result(result: str) -> list[MomentCandidate]:
    payload = extract_json_object(result)
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise CandidateError("discovery JSON must contain candidates list")
    return [validate_candidate(raw) for raw in raw_candidates]


def parse_promotion_result(result: str, candidates: list[MomentCandidate]) -> tuple[list[MomentCandidate], list[dict[str, str]]]:
    payload = extract_json_object(result)
    ranked_raw = payload.get("ranked")
    rejected_raw = payload.get("rejected", [])
    if not isinstance(ranked_raw, list):
        raise CandidateError("promotion JSON must contain ranked list")
    if not isinstance(rejected_raw, list):
        raise CandidateError("promotion JSON rejected must be a list")
    by_key = {c.id: c for c in candidates} | {c.slug: c for c in candidates}
    promoted: list[MomentCandidate] = []
    seen: set[str] = set()
    for item in ranked_raw:
        if not isinstance(item, dict):
            raise CandidateError("ranked entries must be objects")
        key = item.get("id")
        if not isinstance(key, str):
            raise CandidateError("ranked entries must include string ids")
        candidate = by_key.get(key.strip())
        if candidate is None:
            raise CandidateError(f"promoted unknown candidate: {key}")
        if candidate.id not in seen:
            promoted.append(candidate)
            seen.add(candidate.id)
    rejected: list[dict[str, str]] = []
    for item in rejected_raw:
        if not isinstance(item, dict):
            raise CandidateError("rejected entries must be objects")
        rejected.append({
            "id": _string(item.get("id"), "rejected.id", required=False)
            or _string(item.get("slug"), "rejected.slug", required=False),
            "reason": _string(item.get("reason"), "rejected.reason"),
        })
    return promoted, rejected


def candidates_dir(logs_path: Path) -> Path:
    return logs_path / "moments" / "candidates"


def write_candidates_jsonl(logs_path: Path, candidates: list[MomentCandidate]) -> Path:
    out_dir = candidates_dir(logs_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{timestamp}.jsonl"
    with out_path.open("w") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate.to_json(), sort_keys=True) + "\n")
    return out_path


def read_candidate_jsonl(path: Path) -> list[MomentCandidate]:
    candidates: list[MomentCandidate] = []
    for line in path.read_text().splitlines():
        if line.strip():
            candidates.append(validate_candidate(json.loads(line)))
    return candidates


def latest_candidate_file(logs_path: Path) -> Path | None:
    files = sorted(candidates_dir(logs_path).glob("*.jsonl"))
    return files[-1] if files else None


def render_accepted_markdown(candidate: MomentCandidate) -> str:
    lines = [
        "---",
        f"title: {candidate.title}",
        f"description: {candidate.description}",
        f"cadence: {candidate.cadence}",
    ]
    if candidate.cadence == "scheduled":
        lines.append(f"schedule: {candidate.schedule}")
    if candidate.cadence == "trigger":
        lines.append(f"trigger: {candidate.trigger}")
    lines.extend([
        f"confidence: {candidate.confidence:.2f}",
        f"usefulness: {candidate.usefulness}",
        "---",
        "",
        "## Specific Instructions for Agent",
        "",
        candidate.specific_instructions,
        "",
        "## Desired Artifact",
        "",
        candidate.desired_artifact,
        "",
        "## Evidence",
        "",
    ])
    lines.extend(f"- {item}" for item in (candidate.evidence or ["(none supplied)"]))
    lines.extend([
        "",
        "## Source Paths",
        "",
    ])
    lines.extend(f"- `{item}`" for item in (candidate.source_paths or ["(none supplied)"]))
    lines.extend([
        "",
        "## User Value",
        "",
        candidate.user_value,
        "",
        "## Why Now",
        "",
        candidate.why_now,
        "",
    ])
    return "\n".join(lines)


def write_accepted_moment(tada_dir: Path, candidate: MomentCandidate) -> Path:
    topic_dir = tada_dir / candidate.topic
    topic_dir.mkdir(parents=True, exist_ok=True)
    out_path = topic_dir / f"{candidate.slug}.md"
    out_path.write_text(render_accepted_markdown(candidate))
    return out_path
