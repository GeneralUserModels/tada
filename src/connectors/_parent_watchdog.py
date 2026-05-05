"""Best-effort parent-death watchdog for connector subprocesses."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_started = False


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_parent_watchdog() -> None:
    """Terminate this process if its owning Tada server process disappears.

    MCP stdio starts connector servers in their own process groups. That is good
    for killing connector process trees, but it also means an outer process-group
    kill can miss them. This watchdog makes the connector process responsible for
    exiting if the parent server dies before graceful MCP cleanup runs.
    """
    global _started
    if _started:
        return

    parent_pid_raw = os.environ.get("TADA_PARENT_PID")
    if not parent_pid_raw:
        return

    try:
        parent_pid = int(parent_pid_raw)
    except ValueError:
        logger.warning("Ignoring invalid TADA_PARENT_PID=%r", parent_pid_raw)
        return

    if parent_pid <= 1 or parent_pid == os.getpid():
        return

    initial_ppid = os.getppid()
    _started = True

    def watch() -> None:
        while True:
            time.sleep(1.0)
            parent_changed = initial_ppid == parent_pid and os.getppid() != parent_pid
            parent_missing = not _pid_exists(parent_pid)
            if parent_changed or parent_missing:
                logger.warning("Parent process %s disappeared; exiting connector", parent_pid)
                os._exit(143)

    thread = threading.Thread(target=watch, name="tada-parent-watchdog", daemon=True)
    thread.start()
