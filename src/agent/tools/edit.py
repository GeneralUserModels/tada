from pathlib import Path

from .base_tool import BaseTool


class EditTool(BaseTool):
    def __init__(self):
        super().__init__("edit_file", "Replace exact text in file.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file to edit"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The exact text to find and replace"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The text to replace it with"
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }
        )

    def run(self, path: str, old_text: str, new_text: str):
        workdir = Path.cwd()
        resolved = (workdir / path).resolve()
        content = resolved.read_text()
        count = content.count(old_text)
        if count == 0:
            return f"Error: old_text not found in {path}"
        if count > 1:
            return f"Error: old_text found {count} times in {path}, must be unique"
        content = content.replace(old_text, new_text, 1)
        resolved.write_text(content)
        return f"Edited {path}"
