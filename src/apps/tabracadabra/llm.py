"""Shared LLM helpers for tabracadabra — used by both the event-tap service and the onboarding route."""

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


def load_prompt_text_only() -> str:
    """Load a text-only variant of the tab prompt (no screenshot references)."""
    return (_PROMPTS / "tab_text_only.txt").read_text()


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


def stream_text_completion(*, model: str, api_key: str | None, user_text: str):
    """Streaming text completion without screenshots — for onboarding demo."""
    prompt_text = load_prompt_text_only()
    messages = [{"role": "user", "content": f"{prompt_text}\n\n{user_text}"}]
    return completion_with_retry(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        api_key=api_key or None,
        metadata={"app": "tabracadabra"},
    )
