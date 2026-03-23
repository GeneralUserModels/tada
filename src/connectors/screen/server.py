"""Screen MCP server — record screen activity, label in chunks, serve via MCP."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from queue import Empty

from mcp.server.fastmcp import FastMCP

from connectors.screen.napsack import Labeler, OnlineRecorder

logger = logging.getLogger(__name__)

MIN_CHUNK = 10

_recorder: OnlineRecorder | None = None
_labeler: Labeler | None = None
_buffer: list = []


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:  # type: ignore[type-arg]
    global _recorder, _labeler, _buffer
    log_dir = os.environ["POWERNAP_LOG_DIR"]
    _recorder = OnlineRecorder(
        fps=int(os.environ.get("POWERNAP_FPS", "5")),
        buffer_seconds=int(os.environ.get("POWERNAP_BUFFER_SECONDS", "120")),
        log_dir=log_dir,
    )
    _recorder.start()
    _labeler = Labeler(
        chunk_size=int(os.environ.get("POWERNAP_CHUNK_SIZE", "60")),
        log_dir=f"{log_dir}/screen",
        model=os.environ["POWERNAP_LABEL_MODEL"],
    )
    _buffer = []
    yield
    if _recorder is not None:
        _recorder.stop()


mcp = FastMCP("powernap-screen", lifespan=lifespan)


@mcp.tool()
def fetch_screen(since: float | None = None) -> str:
    """Fetch labeled screen activity chunks from the recorder buffer."""
    global _buffer
    if _recorder is None or _labeler is None:
        return json.dumps([])

    while True:
        try:
            _buffer.append(_recorder.aggregation_queue.get_nowait())
        except Empty:
            break

    if len(_buffer) < MIN_CHUNK:
        return json.dumps([])

    chunk, _buffer = _buffer[:MIN_CHUNK], _buffer[MIN_CHUNK:]
    logger.info("screen: labeling chunk of %d aggregations", len(chunk))
    labels = _labeler.label_chunk(chunk)
    return json.dumps([
        {
            "id": label["start_time"],
            "summary": label["text"],
            "img": label.get("img"),
            "screenshot_path": label.get("screenshot_path"),
            "raw_events": label.get("raw_events", []),
        }
        for label in labels
    ])


if __name__ == "__main__":
    mcp.run(transport="stdio")
