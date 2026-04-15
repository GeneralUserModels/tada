"""Lightweight streaming text completion endpoint — used by the onboarding tutorial."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.tabracadabra.llm import stream_text_completion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["completions"])


class _CompletionRequest(BaseModel):
    text: str


@router.post("/completions/stream")
async def stream_completion(request: Request, body: _CompletionRequest):
    config = request.app.state.server.config

    model = config.tabracadabra_model
    api_key = config.resolve_api_key("tabracadabra_api_key")

    def generate():
        try:
            stream = stream_text_completion(
                model=model,
                api_key=api_key,
                user_text=body.text,
            )
            for chunk in stream:
                piece = chunk.choices[0].delta.content or "" if chunk.choices else ""
                if piece:
                    yield piece
        except Exception:
            logger.warning("completions/stream failed", exc_info=True)

    return StreamingResponse(generate(), media_type="text/plain")
