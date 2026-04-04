"""DataManager: watches log_dir for new filtered.jsonl entries across all connectors."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class _JournalHandler(FileSystemEventHandler):
    def __init__(self, data_manager: "DataManager"):
        self._dm = data_manager

    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path).name == "filtered.jsonl":
            self._dm._on_file_changed(Path(event.src_path))

    def on_created(self, event):
        self.on_modified(event)


class DataManager:
    """Loads and watches log_dir/*/filtered.jsonl, maintaining a unified in-memory buffer.

    Canonical buffer item schema:
        {"timestamp": float, "text": str, "dense_caption": str,
         "source_name": str, "prediction_event": bool, "img_path": str | None}
    """

    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.buffer: list = []
        self.labels_processed: int = 0
        self._file_offsets: dict = {}  # str(path) -> bytes already read
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._label_event: Optional[asyncio.Event] = None
        self._observer: Optional[Observer] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {"labels_processed": self.labels_processed}

    async def wait_for_label(self) -> None:
        """Block until a new prediction_event entry arrives via watchdog."""
        self._label_event.clear()
        await self._label_event.wait()

    async def start(self) -> None:
        """Start watchdog and load existing JSONL files. Call once from async context."""
        self._loop = asyncio.get_running_loop()
        self._label_event = asyncio.Event()
        await self._loop.run_in_executor(None, self._load_existing)
        self._observer = Observer()
        self._observer.schedule(_JournalHandler(self), str(self.log_dir), recursive=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._observer.start()
        logger.info(f"DataManager: watching {self.log_dir} ({len(self.buffer)} events loaded)")

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_existing(self) -> None:
        all_entries = []
        for jsonl_path in sorted(self.log_dir.glob("*/filtered.jsonl")):
            all_entries.extend(self._read_new_lines(jsonl_path))
        all_entries.sort(key=lambda e: e["timestamp"])
        self.buffer = all_entries
        self.labels_processed = sum(1 for e in all_entries if e.get("prediction_event"))

    def _read_new_lines(self, path: Path) -> list:
        """Read lines from path starting at the stored byte offset."""
        key = str(path)
        offset = self._file_offsets.get(key, 0)
        entries = []
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                new_bytes = f.read()
            self._file_offsets[key] = offset + len(new_bytes)
            for line in new_bytes.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    entries.append({
                        "timestamp": raw["timestamp"],
                        "text": raw.get("text", ""),
                        "dense_caption": raw.get("dense_caption", ""),
                        "source_name": raw.get("source_name", ""),
                        "prediction_event": bool(raw.get("prediction_event", False)),
                        "img_path": raw.get("img_path"),
                    })
                except (json.JSONDecodeError, KeyError):
                    pass
        except (OSError, IOError):
            pass
        return entries

    def _on_file_changed(self, path: Path) -> None:
        """Called from watchdog thread on filtered.jsonl change."""
        new_entries = self._read_new_lines(path)
        if not new_entries:
            return
        self.buffer.extend(new_entries)
        new_labels = sum(1 for e in new_entries if e.get("prediction_event"))
        if new_labels > 0:
            self.labels_processed += new_labels
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._label_event.set)
