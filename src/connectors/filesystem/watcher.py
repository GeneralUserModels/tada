"""Watch ~/Desktop, ~/Documents, ~/Downloads for filesystem changes using watchdog."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from connectors.base import Connector

WATCH_DIRS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]


class _Handler(FileSystemEventHandler):
    def __init__(self, event_buffer: list | None = None, lock: threading.Lock | None = None):
        super().__init__()
        self._buffer = event_buffer
        self._lock = lock

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        record = {
            "type": event.event_type,
            "path": event.src_path,
            "timestamp": time.time(),
        }
        if self._buffer is not None:
            with self._lock:
                self._buffer.append(record)
        else:
            sys.stdout.write(json.dumps(record) + "\n")
            sys.stdout.flush()


class FilesystemWatcher:
    """Watches user directories and accumulates events in a buffer."""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._observer = Observer()
        self._handler = _Handler(event_buffer=self._events, lock=self._lock)

    def start(self) -> None:
        for d in WATCH_DIRS:
            if os.path.isdir(d):
                self._observer.schedule(self._handler, d, recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def drain_events(self) -> list[dict]:
        """Return accumulated events and clear the buffer."""
        with self._lock:
            events = self._events.copy()
            self._events.clear()
        return events


class FilesystemConnector(Connector):
    """Wraps a FilesystemWatcher and exposes buffered events as a Connector."""

    def __init__(self) -> None:
        super().__init__()
        self._watcher: FilesystemWatcher | None = None
        self._start_watcher()

    def _start_watcher(self) -> None:
        self._watcher = FilesystemWatcher()
        self._watcher.start()

    def fetch(self) -> list[dict]:
        events = self._watcher.drain_events()
        result = []
        for e in events:
            key = hashlib.md5(f"{e['path']}:{e['type']}:{e['timestamp']}".encode()).hexdigest()
            result.append({**e, "id": key})
        return result

    def pause(self) -> None:
        super().pause()
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def resume(self) -> None:
        super().resume()
        if not self._watcher:
            self._start_watcher()


if __name__ == "__main__":
    handler = _Handler()
    observer = Observer()
    for d in WATCH_DIRS:
        if os.path.isdir(d):
            observer.schedule(handler, d, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
