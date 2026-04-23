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
    "calendar/events.jsonl",
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


def _new_seeker_conversations(logs_dir: str, since: datetime | None) -> list[str]:
    """Return seeker conversation files created after *since*."""
    conv_dir = Path(logs_dir) / "active-conversations"
    if not conv_dir.exists():
        return []
    files = sorted(conv_dir.glob("conversation_*.md"))
    if since is None:
        return [str(f.relative_to(logs_dir)) for f in files]
    return [
        str(f.relative_to(logs_dir))
        for f in files
        if datetime.fromtimestamp(f.stat().st_mtime) > since
    ]


def run(logs_dir: str, model: str, api_key: str | None = None, on_round=None) -> str:
    logs_path = Path(logs_dir).resolve()
    logs_dir = str(logs_path)
    memory_dir = logs_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = memory_dir / ".last_ingest"
    last_ingest = read_checkpoint(checkpoint_path)

    new_sessions = sessions_with_new_content(logs_dir, last_ingest)
    modified_sources = _modified_sources(logs_dir, last_ingest)
    new_convos = _new_seeker_conversations(logs_dir, last_ingest)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + INGEST_TEMPLATE.format(
        memory_dir=str(memory_dir),
        logs_dir=logs_dir,
    )

    if last_ingest is not None and (new_sessions or modified_sources or new_convos):
        sessions_list = "\n".join(f"- {s}/labels.jsonl" for s in new_sessions) if new_sessions else "- (none)"
        sources_list = "\n".join(f"- {s}" for s in modified_sources) if modified_sources else "- (none)"
        convos_list = "\n".join(f"- {c}" for c in new_convos) if new_convos else "- (none)"
        instruction += INCREMENTAL_SECTION.format(
            last_ingest_date=last_ingest.strftime("%Y-%m-%d %H:%M"),
            sessions_list=sessions_list,
            other_sources_list=sources_list,
            new_conversations_list=convos_list,
        )
    elif last_ingest is not None and not new_sessions and not modified_sources and not new_convos:
        instruction += (
            f"\n\n## Note\n\nThe last ingest was on "
            f"**{last_ingest.strftime('%Y-%m-%d %H:%M')}** and there is no new data "
            f"since then. Read the existing wiki and check for opportunities to enrich "
            f"existing pages with web searches or cross-references."
        )

    agent, _ = build_agent(model, logs_dir, api_key=api_key)
    agent.max_rounds = 200
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
