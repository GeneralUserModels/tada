"""Ingest new activity logs into the personal knowledge wiki."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint, sessions_with_new_content


_PROMPTS = Path(__file__).parent / "prompts"
SHARED_WIKI_RULES = (_PROMPTS / "shared" / "wiki.txt").read_text()
SHARED_SOURCE_RULES = (_PROMPTS / "shared" / "sources.txt").read_text()
INVENTORY_RULES = (_PROMPTS / "rules" / "inventory.txt").read_text()
UPDATE_RULES = (_PROMPTS / "rules" / "update.txt").read_text()
FINALIZE_RULES = (_PROMPTS / "rules" / "finalize.txt").read_text()
INVENTORY_TEMPLATE = (_PROMPTS / "inventory.txt").read_text()
UPDATE_TEMPLATE = (_PROMPTS / "update.txt").read_text()
FINALIZE_TEMPLATE = (_PROMPTS / "finalize.txt").read_text()
SCHEMA_TEMPLATE = (_PROMPTS / "schema.md").read_text()

NON_SESSION_SOURCES = [
    "email/filtered.jsonl",
    "calendar/filtered.jsonl",
    "notifications/filtered.jsonl",
    "filesys/filtered.jsonl",
]

SPECIAL_MEMORY_FILES = {"index.md", "log.md", "schema.md"}
INVENTORY_KEYS = {
    "mode",
    "sources_to_read",
    "existing_pages_to_read",
    "likely_pages_to_create",
    "likely_pages_to_update",
    "backfill_sources_to_sample",
    "rationale",
}
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_WIKI_LINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
PREVIEW_MAX_FILES = 20
PREVIEW_MAX_LINES = 8
PREVIEW_MAX_CHARS = 900


@dataclass
class IngestInputs:
    mode: str
    last_ingest: datetime | None
    new_inputs_list: str
    active_conversations: list[Path]
    chats: list[Path]
    audio: list[Path]
    tada_feedback: list[Path]
    sessions: list[str]
    modified_streams: list[str]


def _modified_sources(logs_dir: str, since: datetime | None) -> list[str]:
    """Return non-session source files modified after *since*."""
    if since is None:
        return [s for s in NON_SESSION_SOURCES if (Path(logs_dir) / s).exists()]
    result = []
    for src in NON_SESSION_SOURCES:
        p = Path(logs_dir) / src
        if p.exists() and datetime.fromtimestamp(p.stat().st_mtime) > since:
            result.append(src)
    return result


def _new_files_in(base: Path, pattern: str, since: datetime | None) -> list[Path]:
    """Return files matching *pattern* under *base* modified after *since*."""
    if not base.exists():
        return []
    files = sorted(base.rglob(pattern))
    if since is None:
        return files
    return [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) > since]


def _is_hidden_or_special(rel: Path) -> bool:
    return str(rel) in SPECIAL_MEMORY_FILES or any(part.startswith(".") for part in rel.parts)


def _memory_pages(memory_dir: Path) -> list[Path]:
    if not memory_dir.exists():
        return []
    pages: list[Path] = []
    for path in memory_dir.rglob("*.md"):
        rel = path.relative_to(memory_dir)
        if _is_hidden_or_special(rel):
            continue
        pages.append(path)
    return sorted(pages)


def _all_memory_markdown(memory_dir: Path) -> list[Path]:
    if not memory_dir.exists():
        return []
    return sorted(
        p for p in memory_dir.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(memory_dir).parts)
    )


def _bootstrap_memory(memory_dir: Path) -> None:
    """Create deterministic first-run wiki files without overwriting user content."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    index = memory_dir / "index.md"
    log = memory_dir / "log.md"
    schema = memory_dir / "schema.md"
    if not index.exists():
        index.write_text("# Memory Index\n\n")
    if not log.exists():
        log.write_text("# Memory Log\n\n")
    if not schema.exists():
        schema.write_text(SCHEMA_TEMPLATE)


def _section(label: str, items: list, formatter) -> str | None:
    if not items:
        return None
    body = "\n".join(f"- {formatter(item)}" for item in items)
    return f"**{label}:**\n{body}"


def _collect_ingest_inputs(logs_path: Path, last_ingest: datetime | None) -> IngestInputs:
    logs_dir = str(logs_path)
    tada_results = logs_path.parent / "logs-tada" / "results"

    new_active_convos = _new_files_in(logs_path / "active-conversations", "conversation_*.md", last_ingest)
    new_chats = _new_files_in(logs_path / "chats", "conversation.md", last_ingest)
    new_audio = _new_files_in(logs_path / "audio", "*.md", last_ingest)
    new_tada_feedback = _new_files_in(tada_results, "feedback_*.md", last_ingest)
    new_sessions = sessions_with_new_content(logs_dir, last_ingest)
    modified_streams = _modified_sources(logs_dir, last_ingest)

    rel = lambda f: os.path.relpath(f, logs_path)
    sections = [
        _section("Active conversations (user-answered Q&A)", new_active_convos, rel),
        _section("Chats with assistant", new_chats, rel),
        _section("Audio transcripts", new_audio, rel),
        _section("Tada moment feedback", new_tada_feedback, rel),
        _section("Sessions with new screen activity", new_sessions, lambda s: f"{s}/labels.jsonl"),
        _section("Modified streams", modified_streams, str),
    ]
    new_inputs_list = "\n\n".join(s for s in sections if s)
    if last_ingest is None:
        mode = "first_run"
    elif new_inputs_list:
        mode = "incremental"
    else:
        mode = "no_new_data"

    return IngestInputs(
        mode=mode,
        last_ingest=last_ingest,
        new_inputs_list=new_inputs_list or "- (none detected)",
        active_conversations=new_active_convos,
        chats=new_chats,
        audio=new_audio,
        tada_feedback=new_tada_feedback,
        sessions=new_sessions,
        modified_streams=modified_streams,
    )


def _existing_pages_list(memory_dir: Path) -> str:
    pages = _memory_pages(memory_dir)
    if not pages:
        return "- (no existing content pages)"
    return "\n".join(f"- {p.relative_to(memory_dir)}" for p in pages)


def _page_excerpt(path: Path, max_chars: int = 280) -> str:
    if not path.exists():
        return ""
    text = path.read_text()
    if text.startswith("---\n"):
        marker = "\n---\n"
        end = text.find(marker, 4)
        if end != -1:
            text = text[end + len(marker):]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _page_metadata_list(memory_dir: Path, rel_paths: list[str] | None = None) -> str:
    pages: list[Path] = []
    if rel_paths is None:
        pages = _memory_pages(memory_dir)
    else:
        for rel in rel_paths:
            page = memory_dir / rel
            if not page.exists() or page.suffix != ".md":
                continue
            try:
                page_rel = page.relative_to(memory_dir)
            except ValueError:
                continue
            if _is_hidden_or_special(page_rel):
                continue
            pages.append(page)
    if not pages:
        return "- (no content pages)"
    lines = []
    for page in sorted(set(pages)):
        rel = page.relative_to(memory_dir)
        title = _page_title(page)
        excerpt = _page_excerpt(page)
        suffix = f" — {excerpt}" if excerpt else ""
        lines.append(f"- `{rel}` — title: {title}{suffix}")
    return "\n".join(lines)


def _page_title(path: Path) -> str:
    text = path.read_text()
    match = re.search(r"^title:\s*(.+?)\s*$", text, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"')
    return path.stem.replace("-", " ").title()


def _preview_line(line: str) -> str:
    text = re.sub(r"\s+", " ", line).strip()
    if len(text) > PREVIEW_MAX_CHARS:
        return text[:PREVIEW_MAX_CHARS].rstrip() + "..."
    return text


def _file_preview(path: Path, root: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    samples: list[str] = []
    line_count = 0
    with path.open(errors="replace") as f:
        for line in f:
            line_count += 1
            if len(samples) >= PREVIEW_MAX_LINES:
                continue
            sample = _preview_line(line)
            if sample:
                samples.append(sample)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(os.path.relpath(path, root))
    if not samples:
        return f"- `{rel}` ({line_count} lines): (no non-empty preview lines)"
    preview = "\n".join(f"  {i + 1}. {sample}" for i, sample in enumerate(samples))
    return f"- `{rel}` ({line_count} lines):\n{preview}"


def _changed_input_preview(logs_path: Path, inputs: IngestInputs) -> str:
    paths: list[Path] = []
    paths.extend(inputs.active_conversations)
    paths.extend(inputs.chats)
    paths.extend(inputs.audio)
    paths.extend(inputs.tada_feedback)
    paths.extend(logs_path / session / "labels.jsonl" for session in inputs.sessions)
    paths.extend(logs_path / stream for stream in inputs.modified_streams)

    seen: set[Path] = set()
    previews: list[str] = []
    for path in sorted(paths, key=lambda p: os.path.relpath(p, logs_path)):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        preview = _file_preview(path, logs_path)
        if preview:
            previews.append(preview)
        if len(previews) >= PREVIEW_MAX_FILES:
            break
    if not previews:
        return "- (no changed input preview available)"
    suffix = ""
    if len(seen) < len(paths):
        suffix = f"\n- ({len(paths) - len(seen)} additional changed files omitted from preview)"
    return "\n\n".join(previews) + suffix


def _has_frontmatter(path: Path) -> bool:
    text = path.read_text()
    if not text.startswith("---\n"):
        return False
    return "\n---\n" in text[4:]


def _wiki_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in _WIKI_LINK_RE.finditer(text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def _page_identifiers(memory_dir: Path) -> set[str]:
    identifiers: set[str] = set()
    for page in _memory_pages(memory_dir):
        rel = str(page.relative_to(memory_dir))
        stem = rel[:-3] if rel.endswith(".md") else rel
        title = _page_title(page)
        identifiers.update({rel.lower(), stem.lower(), title.lower()})
    return identifiers


def _wiki_link_resolves(target: str, page_identifiers: set[str], index_text: str) -> bool:
    target = target.strip()
    if not target:
        return True
    candidates = {target.lower()}
    if not target.endswith(".md"):
        candidates.add(f"{target}.md".lower())
    if any(candidate in page_identifiers for candidate in candidates):
        return True
    index_lower = index_text.lower()
    return any(candidate in index_lower for candidate in candidates)


def _validate_wiki(memory_dir: Path, today: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    index_path = memory_dir / "index.md"
    log_path = memory_dir / "log.md"
    if not index_path.exists():
        issues.append({"code": "missing_special_file", "path": "index.md", "message": "index.md is missing"})
    if not log_path.exists():
        issues.append({"code": "missing_special_file", "path": "log.md", "message": "log.md is missing"})

    for page in _memory_pages(memory_dir):
        if not _has_frontmatter(page):
            issues.append({
                "code": "missing_frontmatter",
                "path": str(page.relative_to(memory_dir)),
                "message": "Content page is missing YAML frontmatter",
            })

    index_text = index_path.read_text() if index_path.exists() else ""
    for page in _memory_pages(memory_dir):
        rel_text = str(page.relative_to(memory_dir))
        title = _page_title(page)
        if rel_text not in index_text and title not in index_text:
            issues.append({
                "code": "index_missing_page",
                "path": rel_text,
                "message": "Content page is not represented in index.md by path or title",
            })

    page_identifiers = _page_identifiers(memory_dir)
    seen_unresolved: set[tuple[str, str]] = set()
    for page in _all_memory_markdown(memory_dir):
        rel_text = str(page.relative_to(memory_dir))
        if rel_text == "schema.md":
            continue
        for target in _wiki_link_targets(page.read_text()):
            if _wiki_link_resolves(target, page_identifiers, index_text):
                continue
            key = (rel_text, target)
            if key in seen_unresolved:
                continue
            seen_unresolved.add(key)
            issues.append({
                "code": "unresolved_wiki_link",
                "path": rel_text,
                "target": target,
                "message": f"Wiki link [[{target}]] does not resolve to an existing page or index entry",
            })

    log_text = log_path.read_text() if log_path.exists() else ""
    if f"## {today}" not in log_text:
        issues.append({
            "code": "missing_log_entry",
            "path": "log.md",
            "message": f"log.md needs a dated entry headed '## {today}'",
        })

    return issues


def _format_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str)


def _parse_inventory(result: str, expected_mode: str) -> dict[str, Any]:
    matches = _JSON_BLOCK_RE.findall(result)
    if not matches:
        raise ValueError("Inventory pass did not return a fenced JSON block")
    payload = json.loads(matches[-1])
    missing = INVENTORY_KEYS - set(payload)
    if missing:
        raise ValueError(f"Inventory JSON missing keys: {', '.join(sorted(missing))}")
    if payload.get("mode") != expected_mode:
        raise ValueError(f"Inventory mode {payload.get('mode')!r} did not match expected mode {expected_mode!r}")
    list_keys = INVENTORY_KEYS - {"mode", "rationale"}
    for key in list_keys:
        if not isinstance(payload.get(key), list):
            raise ValueError(f"Inventory JSON key {key!r} must be a list")
    if not isinstance(payload.get("rationale"), str):
        raise ValueError("Inventory JSON key 'rationale' must be a string")
    return payload


def _base_prompt_context(now: str, logs_dir: str, memory_dir: Path) -> dict[str, str]:
    return {
        "now": now,
        "logs_dir": logs_dir,
        "memory_dir": str(memory_dir),
        "shared_wiki_rules": SHARED_WIKI_RULES.format(memory_dir=str(memory_dir)),
        "shared_source_rules": SHARED_SOURCE_RULES.format(logs_dir=logs_dir),
    }


def _inventory_prompt(now: str, logs_dir: str, memory_dir: Path, inputs: IngestInputs) -> str:
    last_ingest_text = (
        inputs.last_ingest.strftime("%Y-%m-%d %H:%M")
        if inputs.last_ingest is not None else "never"
    )
    return INVENTORY_TEMPLATE.format(
        now=now,
        logs_dir=logs_dir,
        memory_dir=str(memory_dir),
        shared_wiki_rules=SHARED_WIKI_RULES.format(memory_dir=str(memory_dir)),
        inventory_rules=INVENTORY_RULES,
        mode=inputs.mode,
        last_ingest_date=last_ingest_text,
        new_inputs_list=inputs.new_inputs_list,
        existing_pages_list=_existing_pages_list(memory_dir),
        existing_page_metadata=_page_metadata_list(memory_dir),
        changed_input_preview=_changed_input_preview(Path(logs_dir), inputs),
    )


def _update_prompt(now: str, logs_dir: str, memory_dir: Path, inputs: IngestInputs, inventory: dict[str, Any]) -> str:
    return UPDATE_TEMPLATE.format(
        **_base_prompt_context(now, logs_dir, memory_dir),
        update_rules=UPDATE_RULES,
        mode=inputs.mode,
        new_inputs_list=inputs.new_inputs_list,
        existing_page_metadata=_page_metadata_list(memory_dir),
        inventory_json=_format_json(inventory),
    )


def _finalize_prompt(
    now: str,
    logs_dir: str,
    memory_dir: Path,
    inputs: IngestInputs,
    inventory: dict[str, Any],
    changed_pages: list[str],
    validation_issues: list[dict[str, str]],
) -> str:
    return FINALIZE_TEMPLATE.format(
        **_base_prompt_context(now, logs_dir, memory_dir),
        finalize_rules=FINALIZE_RULES,
        mode=inputs.mode,
        today=datetime.now().strftime("%Y-%m-%d"),
        new_inputs_list=inputs.new_inputs_list,
        inventory_json=_format_json(inventory),
        changed_pages_list="\n".join(f"- {p}" for p in changed_pages) or "- (none detected)",
        changed_page_metadata=_page_metadata_list(memory_dir, changed_pages),
        all_page_metadata=_page_metadata_list(memory_dir),
        validation_report=_format_json(validation_issues) if validation_issues else "[]",
    )


def _run_agent_pass(
    pass_name: str,
    instruction: str,
    logs_dir: str,
    model: str,
    api_key: str | None,
    on_round,
    subagent_model: str | None,
    subagent_api_key: str | None,
) -> str:
    agent, _ = build_agent(
        model, logs_dir, api_key=api_key,
        subagent_model=subagent_model, subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = 50 if pass_name in {"inventory", "finalize"} else 100
    agent.on_round = on_round
    return agent.run([{"role": "user", "content": instruction}])


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
    memory_dir = logs_path / "memory"
    _bootstrap_memory(memory_dir)

    checkpoint_path = memory_dir / ".last_ingest"
    last_ingest = read_checkpoint(checkpoint_path)
    inputs = _collect_ingest_inputs(logs_path, last_ingest)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    inventory_result = _run_agent_pass(
        "inventory",
        _inventory_prompt(now, logs_dir, memory_dir, inputs),
        logs_dir,
        model,
        api_key,
        on_round,
        subagent_model,
        subagent_api_key,
    )
    inventory = _parse_inventory(inventory_result, inputs.mode)

    before_mtimes = {str(p.relative_to(memory_dir)): p.stat().st_mtime for p in _all_memory_markdown(memory_dir)}
    update_result = _run_agent_pass(
        "update",
        _update_prompt(now, logs_dir, memory_dir, inputs, inventory),
        logs_dir,
        model,
        api_key,
        on_round,
        subagent_model,
        subagent_api_key,
    )
    after_update_mtimes = {str(p.relative_to(memory_dir)): p.stat().st_mtime for p in _all_memory_markdown(memory_dir)}
    changed = sorted(rel for rel, mtime in after_update_mtimes.items() if before_mtimes.get(rel) != mtime)
    today = datetime.now().strftime("%Y-%m-%d")
    validation_issues = _validate_wiki(memory_dir, today)

    finalize_result = _run_agent_pass(
        "finalize",
        _finalize_prompt(now, logs_dir, memory_dir, inputs, inventory, changed, validation_issues),
        logs_dir,
        model,
        api_key,
        on_round,
        subagent_model,
        subagent_api_key,
    )

    final_issues = _validate_wiki(memory_dir, today)
    if final_issues:
        raise RuntimeError(f"Memory ingest validation failed: {_format_json(final_issues)}")

    write_checkpoint(checkpoint_path)

    return (
        "## Inventory\n\n"
        f"{inventory_result}\n\n"
        "## Update\n\n"
        f"{update_result}\n\n"
        "## Finalize\n\n"
        f"{finalize_result}"
    )


if __name__ == "__main__":
    import logging

    from apps.moments.cli_config import resolve_memory_api_key, resolve_memory_model
    from server.cost_tracker import init_cost_tracking

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Ingest activity logs into the personal knowledge wiki")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    tracker = init_cost_tracking()

    model = args.model or resolve_memory_model()
    api_key = args.api_key or resolve_memory_api_key()

    result = run(args.logs_dir, model=model, api_key=api_key)
    print(result)

    snapshot, elapsed = tracker.snapshot()
    total_cost = sum(s["cost"] for s in snapshot.values())
    total_tokens = sum(s["input_tokens"] + s["output_tokens"] for s in snapshot.values())
    logging.getLogger(__name__).info(
        "[cost] ingest finished — $%.4f total, %d tokens, %.0fs", total_cost, total_tokens, elapsed
    )
