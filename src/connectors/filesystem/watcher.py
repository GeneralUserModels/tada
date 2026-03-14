"""Watch ~/Desktop, ~/Documents, ~/Downloads for filesystem changes using watchdog."""
from __future__ import annotations

import json
import os
import sys
import time
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

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
