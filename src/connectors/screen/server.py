"""Screen MCP server — record screen activity, label in chunks, serve via MCP."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from queue import Empty

from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession
from pydantic import AnyUrl

from connectors.screen.napsack import Labeler, OnlineRecorder

logger = logging.getLogger(__name__)

MIN_CHUNK = 10

_recorder: OnlineRecorder | None = None
_labeler: Labeler | None = None
_labeled_queue: asyncio.Queue[dict] | None = None
_active_session: ServerSession | None = None


async def _labeling_loop() -> None:
    """Background task: drain aggregation_queue, label in chunks, notify client."""
    buffer: list = []
    while _recorder is not None and _recorder.running:
        while True:
            try:
                buffer.append(_recorder.aggregation_queue.get_nowait())
            except Empty:
                break

        if len(buffer) < MIN_CHUNK:
            await asyncio.sleep(1)
            continue

        chunk, buffer = buffer[:MIN_CHUNK], buffer[MIN_CHUNK:]
        logger.info("screen: labeling chunk of %d aggregations", len(chunk))
        try:
            labels = await asyncio.to_thread(_labeler.label_chunk, chunk)  # type: ignore[union-attr]
        except Exception:
            logger.exception("screen: labeling failed, dropping chunk")
            continue

        for label in labels:
            await _labeled_queue.put({  # type: ignore[union-attr]
                "id": label["start_time"],
                "summary": label["text"],
                "dense_caption": label.get("dense_caption", ""),
                "screenshot_path": label.get("screenshot_path"),
                "raw_events": label.get("raw_events", []),
            })

        if _active_session is not None:
            try:
                await _active_session.send_resource_updated("screen://activity")
            except Exception:
                logger.exception("screen: failed to send resource updated notification")


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:  # type: ignore[type-arg]
    global _recorder, _labeler, _labeled_queue
    _labeled_queue = asyncio.Queue()
    log_dir = os.environ["POWERNAP_LOG_DIR"]
    _recorder = OnlineRecorder(
        fps=int(os.environ.get("POWERNAP_FPS", "5")),
        buffer_seconds=int(os.environ.get("POWERNAP_BUFFER_SECONDS", "120")),
        log_dir=log_dir,
    )
    _recorder.start()
    _labeler = Labeler(
        log_dir=f"{log_dir}/screen",
        model=os.environ["POWERNAP_LABEL_MODEL"],
    )
    asyncio.create_task(_labeling_loop(), name="screen-labeler")
    yield
    if _recorder is not None:
        _recorder.stop()


mcp = FastMCP("powernap-screen", lifespan=lifespan)


@mcp._mcp_server.subscribe_resource()
async def _on_subscribe(_uri: AnyUrl) -> None:
    global _active_session
    _active_session = mcp._mcp_server.request_context.session


@mcp.tool()
async def fetch_screen(since: float | None = None) -> str:  # noqa: ARG001 — queue-based, since is unused
    """Drain all available labeled screen activity chunks from the buffer."""
    if _labeled_queue is None:
        return json.dumps([])
    results = []
    while True:
        try:
            results.append(_labeled_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
