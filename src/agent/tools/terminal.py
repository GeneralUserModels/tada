import asyncio
import os
import re
import signal
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

    def _blocked_command_reason(self, command: str) -> str | None:
        compact = re.sub(r"\s+", " ", command.strip())
        if re.search(r"(^|[;&|]\s*)find\s+/(?:\s|$)", compact):
            return (
                "Refusing to run root-wide `find /`. Narrow the search to the "
                "project, logs, or output directory, or use `rg --files <dir> | rg <pattern>`."
            )
        if re.search(r"(^|[;&|]\s*)find\s+(?:~|\$HOME)(?:\s|$)", compact):
            return (
                "Refusing to run home-wide `find`. Narrow the search to an explicit "
                "project/logs path, or use `rg --files <dir> | rg <pattern>`."
            )
        return None

    def _decode_timeout_piece(self, value) -> str:
        if not value:
            return ""
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return str(value)

    def run(self, command: str):
        blocked_reason = self._blocked_command_reason(command)
        if blocked_reason:
            return blocked_reason

        wrapped = self._wrap_sandbox(command)
        proc = None
        try:
            proc = subprocess.Popen(
                wrapped,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            stdout, stderr = proc.communicate(timeout=self.TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            if proc and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate() if proc else ("", "")
            partial = self._decode_timeout_piece(stdout)
            err = self._decode_timeout_piece(stderr)
            if err:
                partial += ("\n" if partial else "") + err
            return (partial[:50000] + "\n" if partial else "") + f"(timed out after {self.TIMEOUT_SECONDS}s — narrow the scope and retry)"
        output = stdout
        if stderr:
            output += ("\n" if output else "") + stderr
        return output[:50000] if output else f"(exit code {proc.returncode})"
