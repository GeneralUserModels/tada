import json
from pathlib import Path

from .base_tool import BaseTool


class TaskManager:
    """Shared state for file-backed tasks."""

    def __init__(self, tasks_dir: Path):
        self._dir = tasks_dir
        self._dir.mkdir(exist_ok=True)

    def _next_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in self._dir.glob("task_*.json")]
        return max(ids, default=0) + 1

    def _load(self, tid: int) -> dict | None:
        p = self._dir / f"task_{tid}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def _save(self, task: dict):
        (self._dir / f"task_{task['id']}.json").write_text(json.dumps(task, indent=2))

    def create(self, subject: str, description: str = "") -> str:
        task = {"id": self._next_id(), "subject": subject, "description": description,
                "status": "pending", "owner": None, "blockedBy": [], "blocks": []}
        self._save(task)
        return json.dumps(task, indent=2)

    def get(self, tid: int) -> str:
        task = self._load(tid)
        if not task:
            return f"Error: task {tid} not found"
        return json.dumps(task, indent=2)

    def update(self, tid: int, status: str = None,
               add_blocked_by: list = None, add_blocks: list = None) -> str:
        task = self._load(tid)
        if not task:
            return f"Error: task {tid} not found"
        if status:
            task["status"] = status
            if status == "completed":
                for f in self._dir.glob("task_*.json"):
                    t = json.loads(f.read_text())
                    if tid in t.get("blockedBy", []):
                        t["blockedBy"].remove(tid)
                        self._save(t)
            if status == "deleted":
                (self._dir / f"task_{tid}.json").unlink(missing_ok=True)
                return f"Task {tid} deleted"
        if add_blocked_by:
            if isinstance(add_blocked_by, int):
                add_blocked_by = [add_blocked_by]
            task["blockedBy"] = list(set(task["blockedBy"] + list(add_blocked_by)))
        if add_blocks:
            if isinstance(add_blocks, int):
                add_blocks = [add_blocks]
            task["blocks"] = list(set(task["blocks"] + list(add_blocks)))
        self._save(task)
        return json.dumps(task, indent=2)

    def list_all(self) -> str:
        tasks = [json.loads(f.read_text()) for f in sorted(self._dir.glob("task_*.json"))]
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            m = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            owner = f" @{t['owner']}" if t.get("owner") else ""
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{m} #{t['id']}: {t['subject']}{owner}{blocked}")
        return "\n".join(lines)

    def claim(self, tid: int, owner: str) -> str:
        task = self._load(tid)
        if not task:
            return f"Error: task {tid} not found"
        task["owner"] = owner
        task["status"] = "in_progress"
        self._save(task)
        return f"Claimed task #{tid} for {owner}"


class TaskCreateTool(BaseTool):
    def __init__(self, manager: TaskManager):
        super().__init__("task_create", "Create a persistent file task.",
            {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["subject"]
            }
        )
        self._manager = manager

    def run(self, subject: str, description: str = ""):
        return self._manager.create(subject, description)


class TaskGetTool(BaseTool):
    def __init__(self, manager: TaskManager):
        super().__init__("task_get", "Get task details by ID.",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"}
                },
                "required": ["task_id"]
            }
        )
        self._manager = manager

    def run(self, task_id: int):
        return self._manager.get(task_id)


class TaskUpdateTool(BaseTool):
    def __init__(self, manager: TaskManager):
        super().__init__("task_update", "Update task status or dependencies.",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
                    "add_blocked_by": {"type": "array", "items": {"type": "integer"}},
                    "add_blocks": {"type": "array", "items": {"type": "integer"}}
                },
                "required": ["task_id"]
            }
        )
        self._manager = manager

    def run(self, task_id: int, status: str = None, add_blocked_by: list = None, add_blocks: list = None):
        return self._manager.update(task_id, status, add_blocked_by, add_blocks)


class TaskListTool(BaseTool):
    def __init__(self, manager: TaskManager):
        super().__init__("task_list", "List all tasks.",
            {
                "type": "object",
                "properties": {}
            }
        )
        self._manager = manager

    def run(self):
        return self._manager.list_all()
