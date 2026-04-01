from pathlib import Path

from .base_tool import BaseTool


class ReadTool(BaseTool):
    def __init__(self):
        super().__init__("read_file", "Read file contents.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file to read"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of lines to read"
                    }
                },
                "required": ["path"]
            }
        )

    def run(self, path: str, limit: int = None):
        try:
            workdir = Path.cwd()
            path = (workdir / path).resolve()
            lines = path.read_text().splitlines()
            if limit and limit < len(lines):
                lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
            return "\n".join(lines)[:50000]
        except Exception as e:
            return f"Error: {e}"
