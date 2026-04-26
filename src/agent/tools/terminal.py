import asyncio
import subprocess

from sandbox_runtime import SandboxManager

from .base_tool import BaseTool


class TerminalTool(BaseTool):
    # Subclasses (e.g. ReadOnlyTerminalTool used by tabracadabra) override this
    # for tighter budgets when latency matters more than completeness.
    TIMEOUT_SECONDS: float = 120

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

    def _wrap_sandbox(self, command: str):
        try:
            return asyncio.run(SandboxManager.wrap_with_sandbox(command))
        except RuntimeError:
            # Event loop already running (e.g., Playwright active)
            import threading
            result = [None]
            def _run():
                result[0] = asyncio.run(SandboxManager.wrap_with_sandbox(command))
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            return result[0]

    def run(self, command: str):
        wrapped = self._wrap_sandbox(command)
        try:
            result = subprocess.run(
                wrapped, shell=True, capture_output=True, text=True, timeout=self.TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as e:
            partial = (e.stdout or "") + (("\n" + e.stderr) if e.stderr else "")
            return (partial[:50000] + "\n" if partial else "") + f"(timed out after {self.TIMEOUT_SECONDS}s — narrow the scope and retry)"
        output = result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        return output[:50000] if output else f"(exit code {result.returncode})"
