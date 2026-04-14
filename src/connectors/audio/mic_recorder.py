"""Microphone audio recorder using sounddevice."""

import logging
import threading

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1


class MicRecorder:
    """Records microphone audio into a buffer that can be drained by the mixer."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Microphone recorder started (rate=%d)", self.sample_rate)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Microphone recorder stopped")

    def read_and_clear(self) -> np.ndarray | None:
        """Return accumulated samples and reset the buffer. Returns None if empty."""
        with self._lock:
            if not self._buffer:
                return None
            data = np.concatenate(self._buffer)
            self._buffer.clear()
        return data

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            logger.warning("mic: %s", status)
        with self._lock:
            self._buffer.append(indata[:, 0].copy())
