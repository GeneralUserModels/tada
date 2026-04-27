"""Ingest new activity logs into the personal knowledge wiki."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint, sessions_with_new_content


_PROMPTS = Path(__file__).parent / "prompts"
INGEST_TEMPLATE = (_PROMPTS / "ingest.txt").read_text()
INCREMENTAL_SECTION = (_PROMPTS / "ingest_incremental.txt").read_text()

NON_SESSION_SOURCES = [
    "email/filtered.jsonl",
    "calendar/filtered.jsonl",
    "notifications/filtered.jsonl",
    "filesys/filtered.jsonl",
]


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


def run(logs_dir: str, model: str, api_key: str | None = None, on_round=None) -> str:
    logs_path = Path(logs_dir).resolve()
    logs_dir = str(logs_path)
    memory_dir = logs_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = memory_dir / ".last_ingest"
    last_ingest = read_checkpoint(checkpoint_path)

    tada_results = logs_path.parent / "logs-tada" / "results"

    new_active_convos = _new_files_in(logs_path / "active-conversations", "conversation_*.md", last_ingest)
    new_chats = _new_files_in(logs_path / "chats", "conversation.md", last_ingest)
    new_audio = _new_files_in(logs_path / "audio", "*.md", last_ingest)
    new_tada_feedback = _new_files_in(tada_results, "feedback_*.md", last_ingest)
    new_sessions = sessions_with_new_content(logs_dir, last_ingest)
    modified_streams = _modified_sources(logs_dir, last_ingest)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + INGEST_TEMPLATE.format(
        memory_dir=str(memory_dir),
        logs_dir=logs_dir,
    )

    def _section(label: str, items: list, formatter) -> str | None:
        if not items:
            return None
        body = "\n".join(f"- {formatter(item)}" for item in items)
        return f"**{label}:**\n{body}"

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
    has_new = bool(new_inputs_list)

    if last_ingest is not None and has_new:
        instruction += INCREMENTAL_SECTION.format(
            last_ingest_date=last_ingest.strftime("%Y-%m-%d %H:%M"),
            new_inputs_list=new_inputs_list,
            logs_dir=logs_dir,
        )
    elif last_ingest is not None and not has_new:
        instruction += (
            f"\n\n## Note\n\nThe last ingest was on "
            f"**{last_ingest.strftime('%Y-%m-%d %H:%M')}** and there is no new data "
            f"since then. Read the existing wiki and check for opportunities to enrich "
            f"existing pages with web searches or cross-references."
        )

    agent, _ = build_agent(model, logs_dir, api_key=api_key)
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

    parser = argparse.ArgumentParser(description="Ingest activity logs into the personal knowledge wiki")
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
        "[cost] ingest finished — $%.4f total, %d tokens, %.0fs", total_cost, total_tokens, elapsed
    )
