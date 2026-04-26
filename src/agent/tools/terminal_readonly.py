import asyncio
import threading

from sandbox_runtime import SandboxManager
from sandbox_runtime.config import FilesystemConfig, NetworkConfig, SandboxRuntimeConfig

from .terminal import TerminalTool


_READ_ONLY_CONFIG = SandboxRuntimeConfig(
    network=NetworkConfig(allowed_domains=[]),
    filesystem=FilesystemConfig(
        allow_write=[],
        deny_write=[],
        deny_read=["~/.ssh", "~/.gnupg", "~/.aws/credentials"],
    ),
)


class ReadOnlyTerminalTool(TerminalTool):
    # Tabracadabra is in the user's typing-latency budget — anything slower than
    # a few seconds means they've started typing again before we finish.
    TIMEOUT_SECONDS = 3

    def __init__(self):
        super().__init__()
        self.description = "Run a read-only shell command (no filesystem writes, no network). 3s timeout — narrow scope (specific paths, head/tail, --include) instead of broad recursive scans."

    def _wrap_sandbox(self, command: str):
        try:
            return asyncio.run(SandboxManager.wrap_with_sandbox(command, custom_config=_READ_ONLY_CONFIG))
        except RuntimeError:
            result = [None]
            def _run():
                result[0] = asyncio.run(SandboxManager.wrap_with_sandbox(command, custom_config=_READ_ONLY_CONFIG))
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            return result[0]
