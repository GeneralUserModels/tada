"""Mix multiple PCM audio streams into a single WAV buffer."""

import io
import logging

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

SILENCE_RMS_THRESHOLD = 0.005


def mix_and_encode(
    streams: list[np.ndarray],
    sample_rate: int = 16_000,
) -> bytes | None:
    """Mix one or more float32 PCM streams and return WAV bytes.

    Returns None if the result is silence (below RMS threshold).
    """
    if not streams:
        return None

    # Pad shorter streams to match the longest
    max_len = max(len(s) for s in streams)
    padded = [np.pad(s, (0, max_len - len(s))) for s in streams]

    mixed = np.sum(padded, axis=0)
    # Clip to [-1, 1] to avoid distortion
    np.clip(mixed, -1.0, 1.0, out=mixed)

    rms = np.sqrt(np.mean(mixed ** 2))
    if rms < SILENCE_RMS_THRESHOLD:
        logger.debug("audio: chunk is silence (rms=%.4f), skipping", rms)
        return None

    buf = io.BytesIO()
    sf.write(buf, mixed, sample_rate, format="WAV", subtype="FLOAT")
    return buf.getvalue()
