"""Shared LLM helpers for tabracadabra — used by the event-tap service."""

import logging
from pathlib import Path

import httpx
import litellm
from litellm import completion as litellm_completion
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).parent / "prompts"


def load_prompt() -> str:
    """Load the full tab prompt (multimodal, references screenshot)."""
    return (_PROMPTS / "tab.txt").read_text()


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential_jitter(initial=1, max=20, jitter=2),
    retry=retry_if_exception_type((
        litellm.RateLimitError,
        litellm.APIConnectionError,
        litellm.InternalServerError,
        litellm.Timeout,
        httpx.ReadTimeout,
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def completion_with_retry(**kwargs):
    return litellm_completion(**kwargs)
