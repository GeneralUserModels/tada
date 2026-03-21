"""Screen connector — records screen via OnlineRecorder, labels chunks via Labeler."""

from __future__ import annotations

import logging
from pathlib import Path
from queue import Empty

from connectors.base import Connector
from connectors.screen.napsack import Labeler, OnlineRecorder

logger = logging.getLogger(__name__)

# Minimum aggregations to accumulate before triggering a labeling chunk
DEFAULT_MIN_CHUNK = 10


class ScreenConnector(Connector):
    """Drains OnlineRecorder aggregations, labels them in chunks, returns labeled items."""

    def __init__(
        self,
        log_dir: str,
        model: str,
        fps: int = 5,
        buffer_seconds: int = 120,
        chunk_size: int = 60,
        min_chunk: int = DEFAULT_MIN_CHUNK,
    ) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._model = model
        self._fps = fps
        self._buffer_seconds = buffer_seconds
        self._chunk_size = chunk_size
        self._min_chunk = min_chunk
        self._buffer: list = []
        self._recorder = None
        self._labeler = None

    def _start(self) -> None:
        self._recorder = OnlineRecorder(
            fps=self._fps,
            buffer_seconds=self._buffer_seconds,
            log_dir=self._log_dir,
        )
        self._recorder.start()
        self._labeler = Labeler(
            chunk_size=self._chunk_size,
            log_dir=str(Path(self._log_dir) / "screen"),
            model=self._model,
        )
        logger.info("ScreenConnector started")

    def fetch(self, since: float | None = None) -> list[dict]:
        # Lazy-start the recorder on first fetch (supports connectors created in a paused state)
        if not self._recorder:
            self._start()

        # Drain whatever aggregations have accumulated
        while True:
            try:
                self._buffer.append(self._recorder.aggregation_queue.get_nowait())
            except Empty:
                break

        if len(self._buffer) < self._min_chunk:
            return []

        chunk, self._buffer = self._buffer[:self._min_chunk], self._buffer[self._min_chunk:]
        logger.info(f"screen: labeling chunk of {len(chunk)} aggregations")
        labels = self._labeler.label_chunk(chunk)

        return [
            {
                "id": label["start_time"],
                "summary": label["text"],
                "screenshot_path": label.get("screenshot_path"),
                "raw_events": label.get("raw_events", []),
            }
            for label in labels
        ]

    def pause(self) -> None:
        super().pause()
        if self._recorder:
            self._recorder.stop()
            self._recorder = None
            self._labeler = None
            logger.info("ScreenConnector paused")

    def resume(self) -> None:
        super().resume()
        if not self._recorder:
            self._start()
