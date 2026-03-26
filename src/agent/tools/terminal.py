import asyncio
import subprocess

from sandbox_runtime import SandboxManager

from .base_tool import BaseTool


class TerminalTool(BaseTool):
    def __init__(self):
        super().__init__("bash", "Run a shell command (blocking).",
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        )

    def run(self, command: str):
        wrapped = asyncio.run(SandboxManager.wrap_with_sandbox(command))
        result = subprocess.run(
            wrapped, shell=True, capture_output=True, text=True, timeout=120
        )
        output = result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        return output[:50000] if output else f"(exit code {result.returncode})"
