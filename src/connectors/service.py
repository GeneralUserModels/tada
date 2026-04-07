"""Async context logging service — polls connectors, filters via LLM, writes JSONL."""

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from litellm import completion as litellm_completion
from pydantic import BaseModel

from connectors.mcp import MCPConnector

logger = logging.getLogger(__name__)

FILTER_PROMPT = """You are filtering {source} data to keep only items relevant to predicting what a user might do next on their computer.

Here are the items:
{items_json}

Return only the items that are relevant to predicting the user's next actions.
Exclude: marketing emails, spam, noise, temp files, build artifacts, .DS_Store, __pycache__, node_modules, etc.
For each kept item, add a "summary" field with a one-line description of why it's relevant."""


class _FilterItem(BaseModel):
    summary: str
    model_config = {"extra": "allow"}


class _FilterResult(BaseModel):
    items: list[_FilterItem]


@dataclass
class ConnectorConfig:
    name: str
    interval: int        # poll interval in seconds (0 = re-poll immediately after fetch returns)
    log_subdir: str      # subdirectory under log_dir
    connector: MCPConnector
    filter: bool = True           # run LLM filter?
    prediction_event: bool = False  # events from this connector are prediction targets
    requires_auth: str | None = None  # "google", "outlook", or None
    uses_notifications: bool = False  # if True, await server push notification before fetching


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


def _filter_with_llm(items: list[dict], source: str, model: str, api_key: str = "", batch_size: int = 20) -> list[dict]:
    if not items:
        return []
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        logger.info("[llm] connector filter (%s): %d items", source, len(batch))
        response = litellm_completion(
            model=model,
            messages=[{"role": "user", "content": FILTER_PROMPT.format(
                source=source, items_json=json.dumps(batch)
            )}],
            response_format=_FilterResult,
            api_key=api_key or None,
            metadata={"app": "filter"},
        )
        results.extend(item.model_dump() for item in _FilterResult.model_validate_json(response.choices[0].message.content).items)
    return results



async def _run_connector(cfg: ConnectorConfig, log_dir: Path, seen_dir: Path, filter_model: str, filter_api_key: str, state) -> None:
    """Poll a single connector forever: fetch → filter? → write JSONL → update seen."""
    seen_path = seen_dir / f"{cfg.name}.json"
    last_fetched_path = seen_dir / f"{cfg.name}_last_fetched.json"
    seen = _load_seen(seen_path)
    out_path = log_dir / cfg.log_subdir / "filtered.jsonl"

    async def poll():
        if cfg.connector.paused:
            return
        if cfg.uses_notifications:
            notified = await cfg.connector.wait_for_notification(timeout=10.0)
            if not notified:
                return  # timeout with no new data
        since = _load_last_fetched(last_fetched_path)
        logger.info(f"Polling {cfg.name} (since={since})...")
        all_items = await cfg.connector.fetch(since)
        items = [i for i in all_items if i.get("id") and i["id"] not in seen]
        _save_last_fetched(last_fetched_path, time.time())
        if not items:
            logger.info(f"{cfg.name}: no new items")
            return
        if cfg.filter:
            to_write = await asyncio.to_thread(_filter_with_llm, items, cfg.name, filter_model, filter_api_key)
        else:
            to_write = items
        now = time.time()
        
        for item in to_write:
            _append_jsonl(out_path, {
                "timestamp": now,
                "text": item.get("summary", ""),
                "dense_caption": item.get("dense_caption", ""),
                "source": cfg.connector.serialize_item(item),
                "source_name": cfg.name,
                "prediction_event": cfg.prediction_event,
                "img_path": item.get("screenshot_path") if cfg.prediction_event else None,
            })
            if cfg.prediction_event:
                await state.broadcast("label", {"text": item.get("summary", "")[:200]})
            else:
                await state.broadcast("label", {"text": f"[{cfg.name}] {item.get('summary', '')}"[:200]})
        for item in items:
            seen.add(item["id"])
        _trim_seen(seen)
        _save_seen(seen_path, seen)
        logger.info(f"{cfg.name}: fetched {len(items)}, kept {len(to_write)}")

    while True:
        await cfg.connector.disconnect_if_needed()

        # Reconnect notification-based connectors that were resumed but are still disconnected
        if cfg.uses_notifications and not cfg.connector.paused and cfg.connector._session is None:
            try:
                await cfg.connector.connect()
            except Exception:
                logger.exception("%s: failed to reconnect after resume", cfg.name)

        error_occurred = False
        try:
            await poll()
        except RuntimeError as e:
            # MCP tool returned isError=True — extract and display the error
            raw = str(e).removeprefix("MCP tool error: ")
            # Strip "Error executing tool X: " wrapper added by FastMCP
            if raw.startswith("Error executing tool "):
                _, _, raw = raw.partition(": ")
            # Transient network errors — log and retry on next interval, don't disable
            _transient_markers = ("NameResolutionError", "ConnectionError", "RemoteDisconnected",
                                  "Connection aborted", "Max retries exceeded", "timed out",
                                  "ConnectionReset", "NewConnectionError")
            if any(m in raw for m in _transient_markers):
                logger.warning(f"{cfg.name}: transient network error, will retry — {raw}")
                error_occurred = True
            else:
                if "unable to open database file" in raw:
                    user_msg = "Permission denied — grant Full Disk Access in System Settings → Privacy & Security"
                elif "No such file or directory" in raw or "FileNotFoundError" in raw:
                    user_msg = "Not signed in"
                elif "401" in raw or "Unauthorized" in raw:
                    user_msg = "Authentication expired — reconnect your account"
                else:
                    user_msg = raw
                logger.warning(f"{cfg.name}: pausing — {user_msg}")
                cfg.connector.stop(error=user_msg)
                await cfg.connector.disconnect_if_needed()
                # Persist so the connector stays paused-with-error across restarts
                if cfg.name not in state.config.disabled_connectors:
                    state.config.disabled_connectors.append(cfg.name)
                state.config.connector_errors[cfg.name] = user_msg
                state.config.save()
                if state is not None:
                    await state.broadcast("connectors", {"name": cfg.name, "error": user_msg, "enabled": False})
                error_occurred = True
        except Exception as e:
            logger.exception(f"{cfg.name} poll failed")
            error_occurred = True
        # For long-poll connectors (interval=0), ensure a minimum backoff on error or when paused
        # to avoid tight-looping. Normal case: re-poll immediately (the tool handled the wait).
        delay = max(cfg.interval, 5) if (error_occurred or cfg.connector.paused) else cfg.interval
        if delay > 0:
            try:
                await asyncio.wait_for(cfg.connector._disconnect_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass


async def run_context_logging_service(state) -> None:
    """Poll all connectors on intervals, filter via LLM, write JSONL."""

    config = state.config

    while not config.default_llm_api_key:
        logger.info("Waiting for default LLM API key...")
        await asyncio.sleep(2)

    log_dir = Path(config.log_dir)
    seen_dir = log_dir / ".seen"

    connector_configs = [
        ConnectorConfig(
            name="screen", interval=0, log_subdir="screen",
            filter=False,           # Gemini already provides captions
            prediction_event=True,  # screen actions are what the model predicts
            requires_auth=None,
            uses_notifications=True,  # server pushes when labeling is done; no polling
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.screen.server"],
                tool_name="fetch_screen",
                subscribe_uri="screen://activity",
                env={
                    "POWERNAP_LOG_DIR": config.log_dir,
                    "POWERNAP_LABEL_MODEL": config.label_model,
                    "POWERNAP_LABEL_API_KEY": config.resolve_api_key("label_model_api_key"),
                    "POWERNAP_FPS": str(config.fps),
                    "POWERNAP_BUFFER_SECONDS": str(config.buffer_seconds),
                    "POWERNAP_COST_APP": "labeler",
                },
                exclude_from_serialization=["img"],
            ),
        ),
        ConnectorConfig(
            name="gmail", interval=300, log_subdir="email",
            requires_auth="google",
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.gmail.server"],
                tool_name="fetch_emails",
                env={"GOOGLE_TOKEN_PATH": config.google_token_path},
            ),
        ),
        ConnectorConfig(
            name="notifications", interval=0, log_subdir="notifications",
            uses_notifications=True,
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.notifications.server"],
                tool_name="fetch_notifications",
                subscribe_uri="notifications://activity",
            ),
        ),
        ConnectorConfig(
            name="filesystem", interval=0, log_subdir="filesys",
            uses_notifications=True,
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.filesystem.server"],
                tool_name="fetch_changes",
                subscribe_uri="filesystem://changes",
            ),
        ),
        ConnectorConfig(
            name="calendar", interval=900, log_subdir="calendar",
            filter=False,
            requires_auth="google",
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.calendar.server"],
                tool_name="fetch_events",
                env={"GOOGLE_TOKEN_PATH": config.google_token_path},
            ),
        ),
        ConnectorConfig(
            name="outlook_email", interval=300, log_subdir="outlook_email",
            requires_auth="outlook",
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.outlook_email.server"],
                tool_name="fetch_emails",
                env={"OUTLOOK_TOKEN_PATH": config.outlook_token_path},
            ),
        ),
        ConnectorConfig(
            name="outlook_calendar", interval=900, log_subdir="outlook_calendar",
            filter=False,
            requires_auth="outlook",
            connector=MCPConnector(
                command=sys.executable,
                args=["-m", "connectors.outlook_calendar.server"],
                tool_name="fetch_events",
                env={"OUTLOOK_TOKEN_PATH": config.outlook_token_path},
            ),
        ),
    ]

    # Append user-defined community / custom MCP connectors from config
    for mcp_def in config.mcp_connectors:
        connector_configs.append(ConnectorConfig(
            name=mcp_def.name,
            interval=mcp_def.interval,
            log_subdir=mcp_def.log_subdir or mcp_def.name,
            filter=mcp_def.filter,
            prediction_event=mcp_def.prediction_event,
            requires_auth=mcp_def.requires_auth,
            connector=MCPConnector(
                command=mcp_def.command,
                args=mcp_def.args,
                tool_name=mcp_def.tool,
                env=mcp_def.env,
                exclude_from_serialization=mcp_def.exclude_from_serialization,
            ),
        ))

    # Expose connectors on state so routes can pause/resume them
    state.connectors = {c.name: c.connector for c in connector_configs}
    state.connector_auth = {c.name: c.requires_auth for c in connector_configs}

    # Apply persisted enabled/disabled state and error messages from server config
    for cfg in connector_configs:
        if cfg.name in config.disabled_connectors:
            cfg.connector.pause()
        if cfg.name in config.connector_errors:
            cfg.connector.error = config.connector_errors[cfg.name]

    logger.info("Context logging service started")
    filter_api_key = config.resolve_api_key("filter_model_api_key")

    # Eagerly connect notification-based connectors so they can receive push events.
    # Without this, fetch() (which triggers _connect) is never called because the
    # poll loop waits for a notification that can only arrive after subscribing.
    for cfg in connector_configs:
        if cfg.uses_notifications and not cfg.connector.paused:
            try:
                await cfg.connector.connect()
            except Exception:
                logger.exception("%s: failed to connect on startup", cfg.name)

    await asyncio.gather(*[
        _run_connector(c, log_dir, seen_dir, config.filter_model, filter_api_key, state) for c in connector_configs
    ])
