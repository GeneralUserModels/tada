"""Chat app API: persistent multi-turn chats with a tool-using agent."""

from __future__ import annotations

import asyncio
import json
import logging

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


class MessageBody(BaseModel):
    content: str


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/options")
async def get_options():
    return {
        "models": service.AVAILABLE_MODELS,
        "efforts": list(service.EFFORT_TO_MAX_ROUNDS.keys()),
        "default_model": service.DEFAULT_MODEL,
        "default_effort": service.DEFAULT_EFFORT,
        "effort_max_rounds": service.EFFORT_TO_MAX_ROUNDS,
    }


@router.get("/sessions")
async def list_sessions_endpoint(request: Request):
    state = request.app.state.server
    return service.list_sessions(state)


@router.post("/sessions")
async def create_session_endpoint(body: CreateSessionBody, request: Request):
    state = request.app.state.server
    meta = service.create_session(
        state,
        model=body.model or service.DEFAULT_MODEL,
        effort=body.effort or service.DEFAULT_EFFORT,
        title=body.title,
    )
    return meta


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
    messages.append({"role": "user", "content": body.content})

    return StreamingResponse(
        _stream_response(state, session_id, meta, messages),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Streaming generator ──────────────────────────────────────────


async def _stream_response(state, session_id: str, meta: dict, messages: list[dict]):
    loop = asyncio.get_running_loop()
    step_queue: asyncio.Queue = asyncio.Queue()

    on_round = state.make_round_callback("chat", "Thinking…")

    def on_tool_call(name: str, args: dict):
        summary = service.format_tool_action(name, args)
        step = {"tool": name, "summary": summary}
        loop.call_soon_threadsafe(step_queue.put_nowait, step)
        asyncio.run_coroutine_threadsafe(
            state.broadcast_activity("chat", summary),
            loop,
        )

    agent = await service.build_chat_agent(state, meta, on_round=on_round, on_tool_call=on_tool_call)

    agent_task = asyncio.create_task(asyncio.to_thread(agent.run, messages))

    try:
        while not agent_task.done():
            getter = asyncio.create_task(step_queue.get())
            done, _pending = await asyncio.wait(
                {getter, agent_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if getter in done:
                step = getter.result()
                yield f"data: {json.dumps({'step': step})}\n\n"
            else:
                getter.cancel()

        # Drain anything remaining
        while not step_queue.empty():
            step = step_queue.get_nowait()
            yield f"data: {json.dumps({'step': step})}\n\n"

        result = agent_task.result()

        # Persist mutated message list (includes tool calls + final assistant)
        service.save_session(state, session_id, meta, messages)

        yield f"data: {json.dumps({'token': result})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as e:
        logger.exception("chat stream failed")
        yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
    finally:
        await state.broadcast_activity("chat", None)
