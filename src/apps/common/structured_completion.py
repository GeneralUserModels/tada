"""LiteLLM structured-output helper."""

from __future__ import annotations

from typing import TypeVar

import httpx
import litellm
from litellm import completion as litellm_completion
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from apps.common.structured_ops import StructuredOpsError

T = TypeVar("T", bound=BaseModel)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=30, jitter=3),
    retry=retry_if_exception_type((
        litellm.RateLimitError,
        litellm.APIConnectionError,
        litellm.InternalServerError,
        litellm.Timeout,
        httpx.ReadTimeout,
    )),
    reraise=True,
)
def _litellm_structured_completion(**kwargs):
    return litellm_completion(**kwargs)


def structured_completion(
    *,
    model: str,
    instruction: str,
    response_model: type[T],
    api_key: str | None = None,
    metadata_app: str = "structured_completion",
    max_tokens: int = 16000,
) -> tuple[str, T]:
    """Run a single structured LiteLLM call and validate the JSON payload."""
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": instruction}],
        "api_key": api_key or None,
        "max_tokens": max_tokens,
        "metadata": {"app": metadata_app},
    }
    kwargs.update({
        "response_format": response_model,
        "enable_json_schema_validation": True,
    })
    try:
        response = _litellm_structured_completion(**kwargs)
    except litellm.JSONSchemaValidationError as exc:
        raw = getattr(exc, "raw_response", "")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = response_model.model_validate_json(raw)
            except ValidationError:
                pass
            else:
                return raw, parsed
        raise StructuredOpsError(f"structured output validation failed: {raw}") from exc
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        text = tool_calls[0].function.arguments
    else:
        text = message.content or ""
    try:
        parsed = response_model.model_validate_json(text)
    except ValidationError as exc:
        raise StructuredOpsError(f"structured output validation failed: {exc}") from exc
    return text, parsed
