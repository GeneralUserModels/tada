"""Async labeling service — reads from aggregation_queue, labels via Gemini, pushes to label_queue + inference_buffer.

Refactored from napsack/pipeline.py to consume from an asyncio.Queue (fed by HTTP endpoint)
instead of recorder.iter_aggregations().
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

_TIMEOUT = object()  # sentinel for queue timeout


class _AggregationAdapter:
    """Adapts the dict from the HTTP endpoint to look like a ProcessedAggregation
    so the existing Labeler.alabel_chunk() code works unchanged.

    The Labeler expects objects with:
      .screenshot  — an object with .data (numpy array) or None
      .request.timestamp, .request.end_timestamp, .request.reason, etc.
      .events — list of event dicts
    """

    class _Screenshot:
        def __init__(self, pil_img: Image.Image):
            import numpy as np
            self.data = np.array(pil_img)

    class _Request:
        def __init__(self, d: dict):
            self.timestamp = d.get("timestamp", 0.0)
            self.end_timestamp = d.get("end_timestamp", 0.0)
            self.reason = d.get("reason", "")
            self.event_type = d.get("event_type", "")
            self.request_state = d.get("request_state", "")
            self.screenshot_path = None
            self.screenshot_timestamp = d.get("screenshot_timestamp", 0.0)
            self.end_screenshot_timestamp = d.get("end_screenshot_timestamp", 0.0)
            self.monitor = d.get("monitor", {})
            self.burst_id = d.get("burst_id", "")
            self.scale_factor = d.get("scale_factor", 1.0)

    def __init__(self, d: dict):
        pil_img = d.get("screenshot")
        self.screenshot = self._Screenshot(pil_img) if pil_img is not None else None
        self.request = self._Request(d)
        self.events = d.get("events", [])


async def run_labeling_service(state: Any):
    """Main labeling coroutine — runs until task cancellation (server shutdown).

    When recording_active is True: fetches from aggregation_queue, accumulates
    chunks, labels via Gemini, pushes to label_queue + inference_buffer.
    When recording_active is False (paused): drains pending chunks, then idles.
    chunk_buffer and pending_chunks are preserved across pause/resume cycles.
    """
    from powernap.server.ws.handler import broadcast

    config = state.config

    # Lazy-init labeler
    if state.labeler is None:
        from connectors.screen.napsack import Labeler
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        session_dir = log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir.mkdir(parents=True, exist_ok=True)

        state.labeler = Labeler(
            chunk_size=config.chunk_size,
            fps=config.chunk_fps,
            max_workers=config.chunk_workers,
            log_dir=str(session_dir),
            save_screenshots=True,
            model=config.label_model,
        )

    labeler = state.labeler
    agg_queue = state.aggregation_queue
    max_inference_buf = config.past_len + config.future_len + 50  # generous margin for pending evals

    label_count = 0
    chunk_count = 0
    chunk_buffer = []
    pending_chunks: deque = deque()  # (asyncio.Task, list, submit_time)

    while True:
        try:
            # When paused: drain pending_chunks but don't fetch new items
            if not state.recording_active:
                # Drain completed chunks
                while pending_chunks and pending_chunks[0][0].done():
                    task, chunk_aggs, t0 = pending_chunks.popleft()
                    try:
                        labeled_list = task.result()
                    except Exception as e:
                        logger.warning(f"Label chunk failed: {e}. Skipping chunk.")
                        continue
                    latency = time.time() - t0
                    for labeled in labeled_list:
                        if not labeled.get("text"):
                            continue
                        label_count += 1
                        state.labels_processed = label_count
                        text_preview = labeled["text"][:80]
                        logger.info(f"Labeled action #{label_count}: {text_preview}... ({latency:.2f}s)")
                        state.inference_buffer.append(labeled)
                        if len(state.inference_buffer) > max_inference_buf:
                            trim = len(state.inference_buffer) - max_inference_buf
                            del state.inference_buffer[:trim]
                            state.inference_buffer_trim_offset += trim
                        await state.label_queue.put(labeled)
                        state.untrained_batches = state.label_queue.qsize()
                        await broadcast(state, "label", {
                            "count": label_count,
                            "text": labeled["text"][:200],
                        })

                await state.recording_resumed.wait()
                continue

            # Active: fetch from aggregation queue
            wait_set = set()
            fetch_task = asyncio.create_task(_get_from_queue(agg_queue))
            wait_set.add(fetch_task)

            if pending_chunks:
                wait_set.add(pending_chunks[0][0])

            done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED, timeout=2.0)

            # Handle fetch completion
            if fetch_task in done:
                agg_data = fetch_task.result()
                if agg_data is not _TIMEOUT and agg_data is not None:
                    adapted = _AggregationAdapter(agg_data)
                    if adapted.screenshot is not None:
                        chunk_buffer.append(adapted)

                        if len(chunk_buffer) >= labeler.chunk_size:
                            chunk_count += 1
                            logger.info(f"Submitting chunk #{chunk_count} with {len(chunk_buffer)} aggregations")
                            task = asyncio.create_task(labeler.alabel_chunk(chunk_buffer.copy()))
                            pending_chunks.append((task, chunk_buffer.copy(), time.time()))
                            chunk_buffer.clear()
            else:
                fetch_task.cancel()
                try:
                    await fetch_task
                except asyncio.CancelledError:
                    pass

            # Drain completed chunks from the front
            while pending_chunks and pending_chunks[0][0].done():
                task, chunk_aggs, t0 = pending_chunks.popleft()
                try:
                    labeled_list = task.result()
                except Exception as e:
                    logger.warning(f"Label chunk failed: {e}. Skipping chunk.")
                    continue
                latency = time.time() - t0

                for labeled in labeled_list:
                    if not labeled.get("text"):
                        continue

                    label_count += 1
                    state.labels_processed = label_count

                    text_preview = labeled["text"][:80]
                    logger.info(f"Labeled action #{label_count}: {text_preview}... ({latency:.2f}s)")

                    # Push to both queues
                    state.inference_buffer.append(labeled)
                    if len(state.inference_buffer) > max_inference_buf:
                        trim = len(state.inference_buffer) - max_inference_buf
                        del state.inference_buffer[:trim]
                        state.inference_buffer_trim_offset += trim
                    await state.label_queue.put(labeled)
                    state.untrained_batches = state.label_queue.qsize()

                    # Broadcast label event
                    await broadcast(state, "label", {
                        "count": label_count,
                        "text": labeled["text"][:200],
                    })

            # Broadcast status update periodically
            await broadcast(state, "status", {
                "recording_active": state.recording_active,
                "training_active": state.training_active,
                "inference_active": state.inference_active,
                "untrained_batches": state.label_queue.qsize(),
                "labels_processed": label_count,
                "inference_buffer_size": len(state.inference_buffer),
            })

        except asyncio.CancelledError:
            logger.info(f"Labeling service cancelled: {label_count} labels, {chunk_count} chunks")
            break


async def _get_from_queue(queue: asyncio.Queue, timeout: float = 2.0):
    """Get an item from an asyncio.Queue with timeout, returning _TIMEOUT sentinel on timeout."""
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return _TIMEOUT
