from .base_tool import BaseTool


class PlanState:
    def __init__(self):
        self.summary = ""
        self.items: list[dict] = []
        self._next_id = 1

    def add_items(self, contents: list[str]) -> list[dict]:
        added = []
        for content in contents:
            item = {"id": self._next_id, "content": content, "status": "pending"}
            self.items.append(item)
            added.append(item)
            self._next_id += 1
        return added

    def render(self) -> str:
        parts = []
        if self.summary:
            parts.append(f"## Plan\n{self.summary}")
        if self.items:
            lines = []
            for item in self.items:
                marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item["status"]]
                lines.append(f"{marker} #{item['id']} {item['content']}")
            done = sum(1 for t in self.items if t["status"] == "completed")
            lines.append(f"\n({done}/{len(self.items)} completed)")
            parts.append("\n".join(lines))
        return "\n\n".join(parts) if parts else "No plan yet."


class PlanWriteTool(BaseTool):
    def __init__(self, state: PlanState):
        super().__init__("PlanWrite", "Set or replace the plan summary and/or all todo items. Use for initial planning or major plan overhauls.",
            {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "High-level plan narrative — what you're doing and why"
                    },
                    "items": {
                        "type": "array",
                        "description": "Replace all todo items. Omit to keep existing items unchanged.",
                        "items": {"type": "string"}
                    }
                }
            }
        )
        self._state = state

    def run(self, summary: str | None = None, items: list[str] | None = None):
        if summary is not None:
            self._state.summary = summary
        if items is not None:
            if len(items) > 20:
                return "Error: max 20 items allowed"
            self._state.items = []
            self._state._next_id = 1
            self._state.add_items(items)
        return self._state.render()


class PlanUpdateTool(BaseTool):
    def __init__(self, state: PlanState):
        super().__init__("PlanUpdate", "Granular plan updates: add, remove, or update individual items.",
            {
                "type": "object",
                "properties": {
                    "add": {
                        "type": "array",
                        "description": "New items to add (status defaults to pending)",
                        "items": {"type": "string"}
                    },
                    "remove": {
                        "type": "array",
                        "description": "Item IDs to remove",
                        "items": {"type": "integer"}
                    },
                    "update": {
                        "type": "array",
                        "description": "Update existing items by ID",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                                "content": {"type": "string"}
                            },
                            "required": ["id"]
                        }
                    }
                }
            }
        )
        self._state = state

    def run(self, add: list[str] | None = None, remove: list[int] | None = None, update: list[dict] | None = None):
        if remove:
            ids_to_remove = set(remove)
            before = len(self._state.items)
            self._state.items = [i for i in self._state.items if i["id"] not in ids_to_remove]
            removed = before - len(self._state.items)
            if removed != len(ids_to_remove):
                return f"Error: some IDs not found in {ids_to_remove}"

        if update:
            items_by_id = {i["id"]: i for i in self._state.items}
            for u in update:
                item = items_by_id.get(u["id"])
                if not item:
                    return f"Error: item #{u['id']} not found"
                if "status" in u:
                    if u["status"] not in ("pending", "in_progress", "completed"):
                        return f"Error: invalid status '{u['status']}'"
                    item["status"] = u["status"]
                if "content" in u:
                    item["content"] = u["content"]

        if add:
            total = len(self._state.items) + len(add)
            if total > 20:
                return f"Error: would have {total} items, max 20"
            self._state.add_items(add)

        return self._state.render()
