"""Chat app API: persistent multi-turn chats with a tool-using agent."""

from __future__ import annotations

import asyncio
import json
import logging
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Schemas ──────────────────────────────────────────────────────


class CreateSessionBody(BaseModel):
    model: str | None = None
    effort: str | None = None
    title: str | None = None


class UpdateSessionBody(BaseModel):
    effort: str | None = None
    title: str | None = None


class MessageBody(BaseModel):
    content: str


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/options")
async def get_options(request: Request):
    state = request.app.state.server
    return {
        "models": service.AVAILABLE_MODELS,
        "efforts": list(service.EFFORT_TO_MAX_TOKENS.keys()),
        "default_model": service.default_model(state.config),
        "default_effort": service.DEFAULT_EFFORT,
        "effort_max_tokens": service.EFFORT_TO_MAX_TOKENS,
    }


@router.get("/sessions")
async def list_sessions_endpoint(request: Request):
    state = request.app.state.server
    # Hide empty drafts (no messages sent yet) so they don't appear "saved".
    return [s for s in service.list_sessions(state) if (s.get("message_count") or 0) > 0]


@router.post("/sessions")
async def create_session_endpoint(body: CreateSessionBody, request: Request):
    state = request.app.state.server
    return service.create_session(
        state,
        model=body.model or service.default_model(state.config),
        effort=body.effort or service.DEFAULT_EFFORT,
        title=body.title,
    )


@router.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str, request: Request):
    state = request.app.state.server
    data = service.load_session(state, session_id)
    if data is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {
        "meta": data["meta"],
        "messages": service.visible_messages(data["messages"]),
    }


@router.put("/sessions/{session_id}")
async def update_session_endpoint(session_id: str, body: UpdateSessionBody, request: Request):
    state = request.app.state.server
    fields: dict = {}
    if body.effort is not None:
        if body.effort not in service.EFFORT_TO_MAX_TOKENS:
            return JSONResponse({"error": "Invalid effort"}, status_code=400)
        fields["effort"] = body.effort
    if body.title is not None:
        fields["title"] = body.title
    if not fields:
        return JSONResponse({"error": "No fields to update"}, status_code=400)
    meta = service.update_session_meta(state, session_id, **fields)
    if meta is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return meta


@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, request: Request):
    state = request.app.state.server
    ok = service.delete_session(state, session_id)
    if not ok:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"status": "deleted"}


@router.post("/sessions/{session_id}/message")
async def send_message_endpoint(session_id: str, body: MessageBody, request: Request):
    state = request.app.state.server
    data = service.load_session(state, session_id)
    if data is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    if not body.content.strip():
        return JSONResponse({"error": "Message cannot be empty"}, status_code=400)

    meta = data["meta"]
    messages = data["messages"]
    is_first = (meta.get("message_count") or 0) == 0
    messages.append({"role": "user", "content": body.content})

    # Persist the user message synchronously, before returning the streaming
    # response. If the client aborts before the generator runs (e.g. user
    # clicks away to a different chat right after hitting send), the message
    # would otherwise be lost — `_stream_response`'s save_session never fires.
    # This guarantees the chat survives in `list_sessions` (message_count >= 1).
    service.save_session(state, session_id, meta, messages)

    return StreamingResponse(
        _stream_response(state, session_id, meta, messages, is_first, body.content),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Streaming generator ──────────────────────────────────────────


async def _stream_response(
    state,
    session_id: str,
    meta: dict,
    messages: list[dict],
    is_first: bool,
    user_content: str,
):
    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue = asyncio.Queue()

    # The activity banner message is "sticky": once a tool action is shown,
    # it stays until the next tool action (or stream end). on_round only
    # advances the progress counters — it doesn't reset the message back to
    # "Thinking…" so the user has time to read what the agent just did.
    current_message = ["Thinking…"]
    stop_event = threading.Event()

    def on_round(num_turns: int, max_turns: int):
        if stop_event.is_set():
            return
        asyncio.run_coroutine_threadsafe(
            state.broadcast_activity(
                "chat", current_message[0],
                num_turns=num_turns, max_turns=max_turns,
            ),
            loop,
        )

    def on_tool_call(name: str, args: dict):
        if stop_event.is_set():
            return
        summary = service.format_tool_action(name, args)
        current_message[0] = summary
        asyncio.run_coroutine_threadsafe(
            state.broadcast_activity("chat", summary),
            loop,
        )

    def on_token(text: str, round_num: int):
        if stop_event.is_set():
            return
        loop.call_soon_threadsafe(
            event_queue.put_nowait, {"token": text, "round": round_num}
        )

    def on_round_end(round_num: int, is_final: bool):
        if stop_event.is_set():
            return
        loop.call_soon_threadsafe(
            event_queue.put_nowait,
            {"round_end": round_num, "is_final": is_final},
        )

    agent = await service.build_chat_agent(
        state, meta,
        on_round=on_round, on_tool_call=on_tool_call,
        on_token=on_token, on_round_end=on_round_end,
        should_stop=stop_event.is_set,
    )

    agent_task = asyncio.create_task(asyncio.to_thread(agent.run, messages))

    title_task = None
    if is_first:
        title_task = asyncio.create_task(_safe_generate_title(state, session_id, meta, user_content))

    cancelled = False
    try:
        while not agent_task.done():
            getter = asyncio.create_task(event_queue.get())
            done, _pending = await asyncio.wait(
                {getter, agent_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if getter in done:
                event = getter.result()
                yield f"data: {json.dumps(event)}\n\n"
            else:
                getter.cancel()

        while not event_queue.empty():
            event = event_queue.get_nowait()
            yield f"data: {json.dumps(event)}\n\n"

        result = agent_task.result()
        service.save_session(state, session_id, meta, messages)

        if title_task is not None:
            title = await title_task
            if title and title != meta.get("title"):
                updated = service.update_session_meta(state, session_id, title=title)
                if updated is not None:
                    meta = updated
                    yield f"data: {json.dumps({'title': title})}\n\n"

        # If streaming forwarded nothing (e.g. tool-only loop ended at max rounds
        # or the model produced empty deltas), surface the final text once so
        # the client always sees an assistant bubble.
        yield f"data: {json.dumps({'final': result})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except asyncio.CancelledError:
        # Client closed the SSE stream (Stop button). Signal the worker thread
        # to exit at the next round boundary so we stop burning model time.
        cancelled = True
        stop_event.set()
        raise
    except Exception as e:
        logger.exception("chat stream failed")
        yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
    finally:
        if cancelled:
            # Persist whatever partial state the agent produced before cancel.
            # The user message is already in `messages`; saving keeps it visible
            # on reload even if no answer was generated.
            try:
                service.save_session(state, session_id, meta, messages)
            except Exception:
                logger.warning("partial save after cancel failed", exc_info=True)
            if title_task is not None:
                title_task.cancel()
        await state.broadcast_activity("chat", None)


async def _safe_generate_title(state, session_id: str, meta: dict, user_content: str) -> str:
    try:
        return await service.generate_title(state, user_content)
    except Exception as e:
        logger.warning("title generation failed: %s", e)
        return ""
