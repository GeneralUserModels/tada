"""Watch ~/Desktop, ~/Documents, ~/Downloads for filesystem changes using watchdog."""

import json
import os
import sys
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

WATCH_DIRS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]


class _Handler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        record = {
            "type": event.event_type,
            "path": event.src_path,
            "timestamp": time.time(),
        }
        sys.stdout.write(json.dumps(record) + "\n")
        sys.stdout.flush()


class FilesystemWatcher:
    """Watches user directories and outputs JSON lines to stdout."""

    def __init__(self) -> None:
        self._observer = Observer()
        self._handler = _Handler()

    def start(self) -> None:
        for d in WATCH_DIRS:
            if os.path.isdir(d):
                self._observer.schedule(self._handler, d, recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()


if __name__ == "__main__":
    watcher = FilesystemWatcher()
    watcher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
