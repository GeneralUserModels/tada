"""Async context logging service — polls connectors, filters via LLM, writes JSONL."""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

from litellm import completion as litellm_completion

logger = logging.getLogger(__name__)

FILTER_PROMPT = """You are filtering {source} data to keep only items relevant to predicting what a user might do next on their computer.

Here are the items:
{items_json}

Return a JSON array of items that are relevant to predicting the user's next actions.
Exclude: marketing emails, spam, noise, temp files, build artifacts, .DS_Store, __pycache__, node_modules, etc.
For each kept item, add a "summary" field with a one-line description of why it's relevant.

Return ONLY the JSON array, no other text."""


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


def _filter_with_llm(items: list[dict], source: str, model: str) -> list[dict]:
    if not items:
        return []
    response = litellm_completion(
        model=f"gemini/{model}",
        messages=[{"role": "user", "content": FILTER_PROMPT.format(
            source=source, items_json=json.dumps(items)
        )}],
    )
    return json.loads(response.choices[0].message.content)


async def run_context_logging_service(state) -> None:
    """Poll all connectors on intervals, filter via LLM, write JSONL."""
    config = state.config

    # Wait for the Gemini API key to be set (pushed by client after connect)
    while not config.gemini_api_key:
        logger.info("Waiting for Gemini API key...")
        await asyncio.sleep(2)

    log_dir = Path(config.log_dir)

    email_path = log_dir / "email" / "filtered.jsonl"
    notif_path = log_dir / "notifications" / "filtered.jsonl"
    filesys_path = log_dir / "filesys" / "filtered.jsonl"
    calendar_path = log_dir / "calendar" / "events.jsonl"

    seen_dir = log_dir / ".seen"
    seen_email = _load_seen(seen_dir / "email.json")
    seen_notif = _load_seen(seen_dir / "notifications.json")
    seen_calendar = _load_seen(seen_dir / "calendar.json")
    seen_filesys = _load_seen(seen_dir / "filesys.json")

    async def poll_loop(name: str, interval: int, fn):
        """Run fn() immediately then every interval seconds. Log errors, keep retrying."""
        while True:
            try:
                await fn()
            except Exception:
                logger.exception(f"{name} poll failed")
            await asyncio.sleep(interval)

    async def do_email():
        logger.info("Polling email...")
        items = await asyncio.to_thread(_fetch_email, config.gws_path, seen_email)
        _save_seen(seen_dir / "email.json", seen_email)
        if not items:
            return
        filtered = await asyncio.to_thread(_filter_with_llm, items, "email", config.label_model)
        for item in filtered:
            _append_jsonl(email_path, {
                "timestamp": time.time(),
                "text": item.get("summary", ""),
                "source": item,
            })
        logger.info(f"Email: fetched {len(items)}, kept {len(filtered)}")

    async def do_notifications():
        logger.info("Polling notifications...")
        items = await asyncio.to_thread(_fetch_notifications, seen_notif)
        _save_seen(seen_dir / "notifications.json", seen_notif)
        if not items:
            return
        filtered = await asyncio.to_thread(_filter_with_llm, items, "notifications", config.label_model)
        for item in filtered:
            _append_jsonl(notif_path, {
                "timestamp": time.time(),
                "text": item.get("summary", ""),
                "source": item,
            })
        logger.info(f"Notifications: fetched {len(items)}, kept {len(filtered)}")

    async def do_filesystem():
        if not state.filesystem_watcher:
            return
        events = state.filesystem_watcher.drain_events()
        items = _dedup_filesys_events(events, seen_filesys)
        _save_seen(seen_dir / "filesys.json", seen_filesys)
        if not items:
            return
        logger.info(f"Filtering {len(items)} filesystem events...")
        filtered = await asyncio.to_thread(_filter_with_llm, items, "filesystem changes", config.label_model)
        for item in filtered:
            _append_jsonl(filesys_path, {
                "timestamp": time.time(),
                "text": item.get("summary", ""),
                "source": item,
            })
        logger.info(f"Filesystem: fetched {len(items)}, kept {len(filtered)}")

    async def do_calendar():
        logger.info("Polling calendar...")
        events = await asyncio.to_thread(_fetch_calendar, config.gws_path, seen_calendar)
        _save_seen(seen_dir / "calendar.json", seen_calendar)
        for evt in events:
            _append_jsonl(calendar_path, {
                "timestamp": time.time(),
                "text": evt.get("summary", ""),
                "source": evt,
            })
        if events:
            logger.info(f"Calendar: saved {len(events)} events")

    logger.info("Context logging service started")
    await asyncio.gather(
        poll_loop("email", 300, do_email),
        poll_loop("notifications", 120, do_notifications),
        poll_loop("filesystem", 120, do_filesystem),
        poll_loop("calendar", 900, do_calendar),
    )


def _fetch_email(gws_path: str, seen: set[str]) -> list[dict]:
    from connectors.gmail import get_recent_emails
    emails = get_recent_emails(gws_path)
    new = [e for e in emails if e["id"] and e["id"] not in seen]
    for e in new:
        seen.add(e["id"])
    _trim_seen(seen)
    return new


def _fetch_notifications(seen: set[int]) -> list[dict]:
    from connectors.notifications.reader import get_recent_notifications
    notifs = get_recent_notifications()
    new = [n for n in notifs if n["id"] not in seen]
    for n in new:
        seen.add(n["id"])
    _trim_seen(seen)
    return new


def _fetch_calendar(gws_path: str, seen: set[str]) -> list[dict]:
    from connectors.calendar import get_upcoming_events
    events = get_upcoming_events(gws_path)
    new = [e for e in events if e["id"] and e["id"] not in seen]
    for e in new:
        seen.add(e["id"])
    _trim_seen(seen)
    return new


def _dedup_filesys_events(events: list[dict], seen: set[str]) -> list[dict]:
    new = []
    for e in events:
        key = hashlib.md5(f"{e['path']}:{e['type']}:{e['timestamp']}".encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            new.append(e)
    _trim_seen(seen)
    return new


def _trim_seen(seen: set, max_size: int = 10_000) -> None:
    if len(seen) > max_size:
        seen.clear()
