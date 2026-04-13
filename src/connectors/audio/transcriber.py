"""Audio transcription via LiteLLM multimodal + transcript markdown writer."""

import base64
import logging
from datetime import datetime
from pathlib import Path

from litellm import completion as litellm_completion
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

logger = logging.getLogger(__name__)

TRANSCRIPTION_PROMPT = (
    "Transcribe this audio accurately. "
    "Prefix each distinct segment with its timestamp as [MM:SS]. "
    "Return only the transcript text, nothing else. "
    "If the audio is silent or contains no speech, return exactly: [silence]"
)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=10, max=120),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def transcribe_audio(
    wav_bytes: bytes,
    model: str,
    api_key: str | None = None,
    cost_app: str = "transcription",
) -> str:
    """Transcribe WAV audio bytes using LiteLLM multimodal completion.

    Returns the transcript text, or empty string if silence.
    """
    b64_audio = base64.b64encode(wav_bytes).decode("utf-8")

    response = litellm_completion(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "file",
                    "file": {
                        "file_data": f"data:audio/wav;base64,{b64_audio}",
                    },
                },
                {"type": "text", "text": TRANSCRIPTION_PROMPT},
            ],
        }],
        api_key=api_key or None,
        metadata={"app": cost_app},
    )

    text = response.choices[0].message.content.strip()
    if text == "[silence]":
        return ""
    return text


def create_session_file(transcript_dir: Path, session_start: float) -> Path:
    """Create a new markdown file for a recording session. Returns the file path."""
    dt = datetime.fromtimestamp(session_start)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    session_file = transcript_dir / f"{dt.strftime('%Y-%m-%d_%H-%M-%S')}.md"
    session_file.write_text(f"# Audio Transcript — {dt.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    logger.info("audio: created session transcript file %s", session_file)
    return session_file


def append_transcript_markdown(
    session_file: Path,
    text: str,
    chunk_start: float,
    chunk_end: float,
) -> None:
    """Append a 2-min chunk transcript to the session file.

    Each chunk is tagged with its true time range (e.g. 14:23:00 – 14:25:00).
    """
    start_str = datetime.fromtimestamp(chunk_start).strftime("%H:%M:%S")
    end_str = datetime.fromtimestamp(chunk_end).strftime("%H:%M:%S")

    with open(session_file, "a") as f:
        f.write(f"## {start_str} – {end_str}\n\n{text}\n\n---\n\n")
    logger.info("audio: appended transcript chunk (%s – %s) to %s", start_str, end_str, session_file)
