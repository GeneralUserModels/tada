"""Audio MCP server — record mic/system audio, mix, transcribe, serve via MCP."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession
from pydantic import AnyUrl

logger = logging.getLogger(__name__)

CHUNK_SECONDS = 120  # 2 minutes

_mic_recorder = None
_sys_recorder = None
_transcribed_queue: asyncio.Queue[dict] | None = None
_active_session: ServerSession | None = None
_running = False
_session_file: Path | None = None


async def _transcription_loop() -> None:
    """Background task: every CHUNK_SECONDS, mix active streams, transcribe, notify."""
    global _session_file
    from connectors.audio.mixer import mix_and_encode
    from connectors.audio.transcriber import transcribe_audio, append_transcript_markdown

    model = os.environ.get("TADA_TRANSCRIPTION_MODEL", "gemini/gemini-3.1-flash-lite-preview")
    api_key = os.environ.get("TADA_TRANSCRIPTION_API_KEY") or None

    session_path = os.environ.get("TADA_SESSION_FILE", "")
    _session_file = Path(session_path) if session_path else None
    logger.info("audio: session transcript → %s", _session_file)

    chunk_start = time.time()

    while _running:
        await asyncio.sleep(CHUNK_SECONDS)
        if not _running:
            break

        chunk_end = time.time()

        try:
            # Collect PCM from active recorders
            streams: list = []
            if _mic_recorder is not None:
                data = _mic_recorder.read_and_clear()
                if data is not None:
                    streams.append(data)
            if _sys_recorder is not None:
                data = _sys_recorder.read_and_clear()
                if data is not None:
                    streams.append(data)

            if not streams:
                chunk_start = chunk_end
                continue

            wav_bytes = mix_and_encode(streams)
            if wav_bytes is None:
                chunk_start = chunk_end
                continue  # silence

            logger.info("audio: transcribing %.1f KB chunk (%ds)", len(wav_bytes) / 1024, chunk_end - chunk_start)

            text = await asyncio.to_thread(
                transcribe_audio, wav_bytes, model, api_key, cost_app="transcription"
            )

            if not text:
                logger.info("audio: chunk was silence, skipping")
                chunk_start = chunk_end
                continue

            logger.info("audio: transcribed %d chars", len(text))

            item = {
                "id": f"audio_{chunk_end}",
                "summary": text,
                "timestamp": chunk_end,
            }
            await _transcribed_queue.put(item)

            # Append to session transcript with true time range
            if _session_file is not None:
                await asyncio.to_thread(
                    append_transcript_markdown, _session_file, text, chunk_start, chunk_end,
                )

            chunk_start = chunk_end

            # Notify MCP client
            if _active_session is not None:
                await _active_session.send_resource_updated("audio://activity")

        except Exception:
            logger.exception("audio: chunk processing failed, will retry next cycle")
            chunk_start = chunk_end


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    global _mic_recorder, _sys_recorder, _transcribed_queue, _running

    from server.cost_tracker import init_cost_tracking, run_cost_logger
    tracker = init_cost_tracking()
    asyncio.create_task(run_cost_logger(tracker), name="audio-cost-logger")

    _transcribed_queue = asyncio.Queue()
    _running = True

    mic_enabled = os.environ.get("TADA_MIC_ENABLED", "0") == "1"
    sys_enabled = os.environ.get("TADA_SYS_ENABLED", "0") == "1"

    if mic_enabled:
        from connectors.audio.mic_recorder import MicRecorder
        _mic_recorder = MicRecorder()
        _mic_recorder.start()
        logger.info("audio: microphone source enabled")

    if sys_enabled:
        from connectors.audio.sys_recorder import SystemAudioRecorder
        _sys_recorder = SystemAudioRecorder()
        _sys_recorder.start()
        logger.info("audio: system audio source enabled")

    asyncio.create_task(_transcription_loop(), name="audio-transcriber")
    yield

    _running = False
    if _mic_recorder is not None:
        _mic_recorder.stop()
    if _sys_recorder is not None:
        _sys_recorder.stop()


mcp = FastMCP("tada-audio", lifespan=lifespan)


@mcp._mcp_server.subscribe_resource()
async def _on_subscribe(_uri: AnyUrl) -> None:
    global _active_session
    _active_session = mcp._mcp_server.request_context.session


@mcp.tool()
async def fetch_audio(since: float | None = None) -> str:  # noqa: ARG001
    """Drain all available transcribed audio segments."""
    if _transcribed_queue is None:
        return json.dumps([])
    results = []
    while True:
        try:
            results.append(_transcribed_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
