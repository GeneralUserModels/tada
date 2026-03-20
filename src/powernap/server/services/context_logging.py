"""Async context logging service — polls connectors, filters via LLM, writes JSONL."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from litellm import completion as litellm_completion

from connectors.base import Connector
from connectors.calendar import GoogleCalendarConnector
from connectors.filesystem import FilesystemConnector
from connectors.gmail import GmailConnector
from connectors.notifications import NotificationsConnector
from connectors.outlook_calendar import OutlookCalendarConnector
from connectors.outlook_email import OutlookEmailConnector
from connectors.screen import ScreenConnector

logger = logging.getLogger(__name__)

FILTER_PROMPT = """You are filtering {source} data to keep only items relevant to predicting what a user might do next on their computer.

Here are the items:
{items_json}

Return a JSON array of items that are relevant to predicting the user's next actions.
Exclude: marketing emails, spam, noise, temp files, build artifacts, .DS_Store, __pycache__, node_modules, etc.
For each kept item, add a "summary" field with a one-line description of why it's relevant.

Return ONLY the JSON array, no other text."""


@dataclass
class ConnectorConfig:
    name: str
    interval: int        # poll interval in seconds
    log_subdir: str      # subdirectory under log_dir
    connector: Connector
    filter: bool = True  # run LLM filter?


def _append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _load_seen(path: Path) -> set:
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()


def _save_seen(path: Path, seen: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(seen)))


def _load_last_fetched(path: Path) -> float | None:
    return json.loads(path.read_text()) if path.exists() else None


def _save_last_fetched(path: Path, ts: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ts))


def _trim_seen(seen: set, max_size: int = 10_000, keep: int = 9_000) -> None:
    if len(seen) > max_size:
        to_remove = list(seen)[: len(seen) - keep]
        seen.difference_update(to_remove)


def _filter_with_llm(items: list[dict], source: str, model: str, batch_size: int = 20) -> list[dict]:
    if not items:
        return []
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        response = litellm_completion(
            model=f"gemini/{model}",
            messages=[{"role": "user", "content": FILTER_PROMPT.format(
                source=source, items_json=json.dumps(batch)
            )}],
        )
        results.extend(json.loads(response.choices[0].message.content))
    return results


async def _run_connector(cfg: ConnectorConfig, log_dir: Path, seen_dir: Path, label_model: str) -> None:
    """Poll a single connector forever: fetch → filter? → write JSONL → update seen."""
    seen_path = seen_dir / f"{cfg.name}.json"
    last_fetched_path = seen_dir / f"{cfg.name}_last_fetched.json"
    seen = _load_seen(seen_path)
    out_path = log_dir / cfg.log_subdir / "filtered.jsonl"

    async def poll():
        if cfg.connector.paused:
            return
        since = _load_last_fetched(last_fetched_path)
        logger.info(f"Polling {cfg.name} (since={since})...")
        all_items = await asyncio.to_thread(cfg.connector.fetch, since)
        items = [i for i in all_items if i.get("id") and i["id"] not in seen]
        _save_last_fetched(last_fetched_path, time.time())
        if not items:
            logger.info(f"{cfg.name}: no new items")
            return
        if cfg.filter:
            to_write = await asyncio.to_thread(_filter_with_llm, items, cfg.name, label_model)
        else:
            to_write = items
        for item in to_write:
            _append_jsonl(out_path, {"timestamp": time.time(), "text": item.get("summary", ""), "source": item})
        for item in items:
            seen.add(item["id"])
        _trim_seen(seen)
        _save_seen(seen_path, seen)
        logger.info(f"{cfg.name}: fetched {len(items)}, kept {len(to_write)}")

    while True:
        try:
            await poll()
        except Exception:
            logger.exception(f"{cfg.name} poll failed")
        await asyncio.sleep(cfg.interval)


async def run_context_logging_service(state) -> None:
    """Poll all connectors on intervals, filter via LLM, write JSONL."""

    config = state.config

    while not config.gemini_api_key:
        logger.info("Waiting for Gemini API key...")
        await asyncio.sleep(2)

    log_dir = Path(config.log_dir)
    seen_dir = log_dir / ".seen"

    connector_configs = [
        ConnectorConfig(
            name="screen", interval=60, log_subdir="screen",
            connector=ScreenConnector(
                log_dir=config.log_dir,
                model=config.label_model,
                fps=config.fps,
                buffer_seconds=config.buffer_seconds,
                chunk_size=config.chunk_size,
            ),
            filter=False,  # Gemini already provides captions
        ),
        ConnectorConfig(
            name="email", interval=300, log_subdir="email",
            connector=GmailConnector(config.google_token_path),
        ),
        ConnectorConfig(
            name="notifications", interval=120, log_subdir="notifications",
            connector=NotificationsConnector(),
        ),
        ConnectorConfig(
            name="filesystem", interval=120, log_subdir="filesys",
            connector=FilesystemConnector(),
        ),
        ConnectorConfig(
            name="calendar", interval=900, log_subdir="calendar",
            connector=GoogleCalendarConnector(config.google_token_path),
            filter=False,
        ),
        ConnectorConfig(
            name="outlook_email", interval=300, log_subdir="outlook_email",
            connector=OutlookEmailConnector(config.outlook_token_path),
        ),
        ConnectorConfig(
            name="outlook_calendar", interval=900, log_subdir="outlook_calendar",
            connector=OutlookCalendarConnector(config.outlook_token_path),
            filter=False,
        ),
    ]

    # Expose connectors on state so routes can pause/resume them
    state.connectors = {c.name: c.connector for c in connector_configs}

    logger.info("Context logging service started")
    await asyncio.gather(*[
        _run_connector(c, log_dir, seen_dir, config.label_model) for c in connector_configs
    ])
