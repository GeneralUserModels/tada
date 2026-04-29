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
_shutdown_event: asyncio.Event | None = None
_flush_done_event: asyncio.Event | None = None
_session_file: Path | None = None
# Buffers from recorders disabled mid-chunk, drained on next _process_chunk
_leftover_streams: list = []


async def _process_chunk(
    chunk_start: float,
    chunk_end: float,
    model: str,
    api_key: str | None,
) -> None:
    """Collect audio from recorders, mix, transcribe, write, notify."""
    from connectors.audio.mixer import mix_and_encode
    from connectors.audio.transcriber import transcribe_audio, append_transcript_markdown

    streams: list = _leftover_streams.copy()
    leftover_n = len(streams)
    _leftover_streams.clear()
    mic_n = sys_n = 0
    if _mic_recorder is not None:
        data = _mic_recorder.read_and_clear()
        if data is not None:
            streams.append(data)
            mic_n = 1
    if _sys_recorder is not None:
        data = _sys_recorder.read_and_clear()
        if data is not None:
            streams.append(data)
            sys_n = 1
    logger.info(
        "audio: chunk window %.1fs — streams=%d (leftover=%d, mic=%d, sys=%d, mic_recorder=%s, sys_recorder=%s)",
        chunk_end - chunk_start, len(streams), leftover_n, mic_n, sys_n,
        _mic_recorder is not None, _sys_recorder is not None,
    )

    if not streams:
        logger.info("audio: chunk skipped — no active streams (recorders not enabled?)")
        return

    wav_bytes = mix_and_encode(streams)
    if wav_bytes is None:
        logger.info("audio: chunk skipped — mix_and_encode returned None (silence)")
        return

    logger.info("audio: transcribing %.1f KB chunk (%ds)", len(wav_bytes) / 1024, chunk_end - chunk_start)

    text = await asyncio.to_thread(
        transcribe_audio, wav_bytes, model, api_key, cost_app="transcription"
    )

    if not text:
        logger.info("audio: chunk was silence, skipping")
        return

    logger.info("audio: transcribed %d chars", len(text))

    item = {
        "id": f"audio_{chunk_end}",
        "summary": text,
        "timestamp": chunk_end,
    }
    await _transcribed_queue.put(item)
    logger.info("audio: queued transcript (queue size now %d)", _transcribed_queue.qsize())

    if _session_file is not None:
        await asyncio.to_thread(
            append_transcript_markdown, _session_file, text, chunk_start, chunk_end,
        )
        logger.info("audio: appended transcript to %s", _session_file)
    else:
        logger.warning("audio: no session file set — transcript not persisted to disk")

    if _active_session is not None:
        await _active_session.send_resource_updated("audio://activity")
        logger.info("audio: notified subscriber via audio://activity")
    else:
        logger.warning("audio: no active MCP session — labeling pipeline will NOT be notified")


async def _transcription_loop() -> None:
    """Background task: every CHUNK_SECONDS, mix active streams, transcribe, notify."""
    global _session_file

    model = os.environ.get("TADA_TRANSCRIPTION_MODEL", "gemini/gemini-3.1-flash-lite-preview")
    api_key = os.environ.get("TADA_TRANSCRIPTION_API_KEY") or None

    session_path = os.environ.get("TADA_SESSION_FILE", "")
    _session_file = Path(session_path) if session_path else None
    logger.info(
        "audio: transcription loop START — model=%s, api_key=%s, chunk=%ds, session=%s",
        model, "set" if api_key else "missing", CHUNK_SECONDS, _session_file,
    )

    chunk_start = time.time()
    tick = 0

    while not _shutdown_event.is_set():
        tick += 1
        logger.info("audio: loop tick %d — sleeping up to %ds", tick, CHUNK_SECONDS)
        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=CHUNK_SECONDS)
            logger.info("audio: loop tick %d — woke early via shutdown_event", tick)
        except asyncio.TimeoutError:
            logger.info("audio: loop tick %d — woke via %ds timeout (normal)", tick, CHUNK_SECONDS)

        chunk_end = time.time()
        if chunk_end - chunk_start < 1:
            logger.info("audio: loop tick %d — chunk window <1s, exiting loop", tick)
            break
        try:
            await _process_chunk(chunk_start, chunk_end, model, api_key)
        except Exception:
            logger.exception("audio: chunk processing failed")
        chunk_start = chunk_end

    logger.info("audio: transcription loop EXIT after %d ticks", tick)
    if _flush_done_event is not None:
        _flush_done_event.set()


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    global _mic_recorder, _sys_recorder, _transcribed_queue

    logger.info(
        "audio: MCP server lifespan START — env: TADA_MIC_ENABLED=%s, TADA_SYS_ENABLED=%s, TADA_SESSION_FILE=%s",
        os.environ.get("TADA_MIC_ENABLED", "<unset>"),
        os.environ.get("TADA_SYS_ENABLED", "<unset>"),
        os.environ.get("TADA_SESSION_FILE", "<unset>"),
    )

    from server.cost_tracker import init_cost_tracking, run_cost_logger
    tracker = init_cost_tracking()
    asyncio.create_task(run_cost_logger(tracker), name="audio-cost-logger")

    global _shutdown_event, _flush_done_event
    _transcribed_queue = asyncio.Queue()
    _shutdown_event = asyncio.Event()
    _flush_done_event = asyncio.Event()

    mic_enabled = os.environ.get("TADA_MIC_ENABLED", "0") == "1"
    sys_enabled = os.environ.get("TADA_SYS_ENABLED", "0") == "1"

    if mic_enabled:
        from connectors.audio.mic_recorder import MicRecorder
        _mic_recorder = MicRecorder()
        _mic_recorder.start()
        logger.info("audio: microphone source enabled at boot")

    if sys_enabled:
        from connectors.audio.sys_recorder import SystemAudioRecorder
        _sys_recorder = SystemAudioRecorder()
        _sys_recorder.start()
        logger.info("audio: system audio source enabled at boot")

    if not mic_enabled and not sys_enabled:
        logger.info("audio: no recorders enabled at boot — waiting for configure_sources call")

    transcription_task = asyncio.create_task(_transcription_loop(), name="audio-transcriber")
    yield

    # Signal shutdown — wakes the loop from its sleep immediately so it can flush
    _shutdown_event.set()
    await transcription_task
    if _mic_recorder is not None:
        _mic_recorder.stop()
    if _sys_recorder is not None:
        _sys_recorder.stop()


mcp = FastMCP("tada-audio", lifespan=lifespan)


@mcp._mcp_server.subscribe_resource()
async def _on_subscribe(uri: AnyUrl) -> None:
    global _active_session
    _active_session = mcp._mcp_server.request_context.session
    logger.info("audio: subscriber attached for %s — _active_session set", uri)


@mcp.tool()
async def configure_sources(mic_enabled: bool | None = None, sys_enabled: bool | None = None, session_file: str | None = None) -> str:
    """Toggle mic/system audio recorders at runtime without restarting the server."""
    global _mic_recorder, _sys_recorder, _session_file

    logger.info(
        "audio: configure_sources called — mic_enabled=%s, sys_enabled=%s, session_file=%s",
        mic_enabled, sys_enabled, session_file,
    )

    if session_file is not None:
        _session_file = Path(session_file) if session_file else None
        logger.info("audio: session transcript → %s", _session_file)

    if mic_enabled is not None:
        if mic_enabled and _mic_recorder is None:
            from connectors.audio.mic_recorder import MicRecorder
            _mic_recorder = MicRecorder()
            _mic_recorder.start()
            logger.info("audio: microphone source enabled")
        elif not mic_enabled and _mic_recorder is not None:
            data = _mic_recorder.read_and_clear()
            if data is not None:
                _leftover_streams.append(data)
            _mic_recorder.stop()
            _mic_recorder = None
            logger.info("audio: microphone source disabled")

    if sys_enabled is not None:
        if sys_enabled and _sys_recorder is None:
            from connectors.audio.sys_recorder import SystemAudioRecorder
            _sys_recorder = SystemAudioRecorder()
            _sys_recorder.start()
            logger.info("audio: system audio source enabled")
        elif not sys_enabled and _sys_recorder is not None:
            data = _sys_recorder.read_and_clear()
            if data is not None:
                _leftover_streams.append(data)
            _sys_recorder.stop()
            _sys_recorder = None
            logger.info("audio: system audio source disabled")

    return json.dumps({"ok": True, "mic": _mic_recorder is not None, "sys": _sys_recorder is not None})


@mcp.tool()
async def flush_audio() -> str:
    """Flush remaining audio: transcribe whatever is buffered, write to session file. Blocks until done."""
    if _shutdown_event is None or _shutdown_event.is_set():
        return json.dumps({"ok": True, "flushed": False})
    _shutdown_event.set()
    await _flush_done_event.wait()
    return json.dumps({"ok": True, "flushed": True})


@mcp.tool()
async def fetch_audio(since: float | None = None) -> str:  # noqa: ARG001
    """Drain all available transcribed audio segments."""
    if _transcribed_queue is None:
        logger.warning("audio: fetch_audio called but queue is None")
        return json.dumps([])
    results = []
    while True:
        try:
            results.append(_transcribed_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    logger.info("audio: fetch_audio drained %d items", len(results))
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
