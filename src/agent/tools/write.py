from pathlib import Path

from .base_tool import BaseTool


class WriteTool(BaseTool):
    def __init__(self):
        super().__init__("write_file", "Write content to file.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        )

    def run(self, path: str, content: str):
        workdir = Path.cwd()
        resolved = (workdir / path).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
