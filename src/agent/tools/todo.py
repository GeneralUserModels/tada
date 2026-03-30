from .base_tool import BaseTool


class TodoTool(BaseTool):
    def __init__(self):
        super().__init__("TodoWrite", "Update task tracking list.",
            {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                                "activeForm": {"type": "string"}
                            },
                            "required": ["content", "status", "activeForm"]
                        }
                    }
                },
                "required": ["items"]
            }
        )
        self.items = []

    def run(self, items: list):
        if len(items) > 20:
            return "Error: max 20 todos allowed"
        validated = []
        for item in items:
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active_form = str(item.get("activeForm", ""))
            if not content:
                return "Error: content required"
            if status not in ("pending", "in_progress", "completed"):
                return f"Error: invalid status '{status}'"
            validated.append({"content": content, "status": status, "activeForm": active_form})
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines = []
        for item in self.items:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item["status"]]
            lines.append(f"{marker} {item['content']}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)
