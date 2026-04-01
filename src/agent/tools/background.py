import asyncio
import json
import subprocess
import threading
import uuid
from queue import Queue

from sandbox_runtime import SandboxManager

from .base_tool import BaseTool


class BackgroundManager:
    """Shared state for background tasks."""

    def __init__(self):
        self.tasks = {}
        self.notifications = Queue()

    def start(self, command: str, timeout: int = 120) -> str:
        tid = str(uuid.uuid4())[:8]
        self.tasks[tid] = {"status": "running", "command": command, "result": None}
        threading.Thread(target=self._exec, args=(tid, command, timeout), daemon=True).start()
        return f"Background task {tid} started: {command[:80]}"

    def _exec(self, tid: str, command: str, timeout: int):
        try:
            wrapped = asyncio.run(SandboxManager.wrap_with_sandbox(command))
            r = subprocess.run(
                wrapped, shell=True, capture_output=True, text=True, timeout=timeout
            )
            output = (r.stdout + r.stderr).strip()[:50000]
            self.tasks[tid].update({"status": "completed", "result": output or "(no output)"})
        except Exception as e:
            self.tasks[tid].update({"status": "error", "result": str(e)})
        self.notifications.put({
            "task_id": tid,
            "status": self.tasks[tid]["status"],
            "result": self.tasks[tid]["result"][:500]
        })

    def check(self, task_id: str = None) -> str:
        if task_id:
            t = self.tasks.get(task_id)
            if not t:
                return f"Unknown task: {task_id}"
            return f"[{t['status']}] {t.get('result', '(running)')}"
        return "\n".join(
            f"{k}: [{v['status']}] {v['command'][:60]}" for k, v in self.tasks.items()
        ) or "No background tasks."

    def drain(self) -> list:
        notifs = []
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
        return notifs


class BackgroundRunTool(BaseTool):
    def __init__(self, manager: BackgroundManager):
        super().__init__("background_run", "Run command in background thread.",
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)"}
                },
                "required": ["command"]
            }
        )
        self._manager = manager

    def run(self, command: str, timeout: int = 120):
        return self._manager.start(command, timeout)


class CheckBackgroundTool(BaseTool):
    def __init__(self, manager: BackgroundManager):
        super().__init__("check_background", "Check background task status.",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID (optional, omit to list all)"}
                }
            }
        )
        self._manager = manager

    def run(self, task_id: str = None):
        return self._manager.check(task_id)
