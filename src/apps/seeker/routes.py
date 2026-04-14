"""Seeker API — conversation UI backed by LLM streaming."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import litellm
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/seeker", tags=["seeker"])

SYSTEM_PROMPT = """\
You are having a conversation with a user to understand them better. You have a set of questions \
generated from observing their digital activity logs. Your goal is to ask these questions naturally \
in conversation — not as a survey, but as a genuine dialogue.

Guidelines:
- Ask one question at a time. Wait for the answer before moving on.
- Follow up on interesting answers — dig deeper when something is revealing or surprising.
- You don't have to ask every question. Skip ones that feel redundant given what you've learned.
- Be conversational, warm, and direct. You're an AI that's been watching their activity — own that.
- Keep your messages short. A question plus a brief observation or transition, nothing more.
- When you feel you've learned enough or the user seems done, end the conversation.

To end the conversation, include [DONE] at the very end of your message. Before ending, briefly \
summarize what you've learned in 2-3 sentences.

Here are the questions to guide the conversation:

{questions}
"""

DONE_MARKER = "[DONE]"

CLEANUP_PROMPT = """\
Below is a conversation between a Seeker AI and a user, followed by a list of questions the Seeker \
had available. Identify which questions were adequately covered or answered during the conversation. \
A question counts as covered if the conversation addressed its core topic, even if the exact wording \
differed.

Return ONLY the exact heading lines (starting with ##) of the covered questions, one per line. \
If none were covered, return "NONE".

## Conversation

{conversation}

## Questions

{questions}
"""


def _conversations_dir(state) -> Path:
    return Path(state.config.log_dir).resolve() / "active-conversations"


def _questions_path(state) -> Path:
    return _conversations_dir(state) / "questions.md"


def _state_path(state) -> Path:
    return _conversations_dir(state) / "seeker_state.json"


def _load_seeker_state(state) -> dict:
    path = _state_path(state)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_seeker_state(state, data: dict):
    path = _state_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _resolve_api_key(config) -> str | None:
    return config.seeker_api_key or config.moments_agent_api_key or config.resolve_api_key("agent_api_key")


def _has_questions(state) -> bool:
    qp = _questions_path(state)
    return qp.exists() and qp.read_text().strip() != ""


def _parse_conversation_markdown(text: str) -> list[dict]:
    """Parse a saved conversation markdown file back into messages."""
    messages = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("**Seeker:**"):
            content = line.replace("**Seeker:**", "").strip()
            messages.append({"role": "assistant", "content": content})
        elif line.startswith("**User:**"):
            content = line.replace("**User:**", "").strip()
            messages.append({"role": "user", "content": content})
    return messages


def _save_conversation(state) -> str:
    """Save current conversation to disk, return the filename."""
    conversations_dir = _conversations_dir(state)
    conversations_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"conversation_{timestamp}.md"
    output_path = conversations_dir / filename

    lines = ["# Conversation\n"]
    for msg in state.seeker_messages:
        if msg["role"] == "system":
            continue
        if msg["role"] == "assistant":
            text = msg["content"].replace(DONE_MARKER, "").strip()
            lines.append(f"**Seeker:** {text}\n")
        elif msg["role"] == "user":
            lines.append(f"**User:** {msg['content']}\n")

    output_path.write_text("\n".join(lines))
    logger.info(f"Seeker conversation saved to {output_path}")
    return filename


def _build_conversation_text(messages: list[dict]) -> str:
    """Build a plain-text version of the conversation for the cleanup prompt."""
    lines = []
    for msg in messages:
        if msg["role"] == "system":
            continue
        speaker = "Seeker" if msg["role"] == "assistant" else "User"
        text = msg["content"].replace(DONE_MARKER, "").strip()
        lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


async def _cleanup_questions(state):
    """Use LLM to identify covered questions and remove them from questions.md."""
    qp = _questions_path(state)
    if not qp.exists():
        return

    questions_text = qp.read_text().strip()
    if not questions_text:
        return

    conversation_text = _build_conversation_text(state.seeker_messages)
    prompt = CLEANUP_PROMPT.format(conversation=conversation_text, questions=questions_text)

    model = state.config.seeker_model
    api_key = _resolve_api_key(state.config)

    kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if api_key:
        kwargs["api_key"] = api_key

    response = await litellm.acompletion(**kwargs)
    result = response.choices[0].message.content.strip()

    if result == "NONE":
        logger.info("Seeker cleanup: no questions covered")
        return

    covered_headings = set()
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith("##"):
            covered_headings.add(line.strip())

    if not covered_headings:
        logger.info("Seeker cleanup: could not parse covered questions")
        return

    lines = questions_text.split("\n")
    new_lines = []
    skip = False
    for line in lines:
        if line.strip().startswith("## "):
            if line.strip() in covered_headings:
                skip = True
                continue
            else:
                skip = False
        if not skip:
            new_lines.append(line)

    new_text = "\n".join(new_lines).strip()
    if new_text == "# Questions" or not new_text:
        qp.write_text("")
        logger.info(f"Seeker cleanup: all {len(covered_headings)} questions removed")
    else:
        qp.write_text(new_text + "\n")
        logger.info(f"Seeker cleanup: removed {len(covered_headings)} questions, some remain")


async def _end_conversation(state):
    """Save conversation, clean up questions, reset state."""
    filename = _save_conversation(state)
    await _cleanup_questions(state)

    seeker_state = _load_seeker_state(state)
    seeker_state["last_conversation_file"] = filename
    _save_seeker_state(state, seeker_state)

    state.seeker_conversation_active = False
    state.seeker_messages = []

    await state.broadcast("seeker_conversation_ended", {})


async def _stream_llm_response(state):
    """Generator that streams LLM tokens as SSE data lines."""
    model = state.config.seeker_model
    api_key = _resolve_api_key(state.config)

    kwargs = {"model": model, "messages": list(state.seeker_messages), "stream": True}
    if api_key:
        kwargs["api_key"] = api_key

    response = await litellm.acompletion(**kwargs)
    full_text = ""
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            full_text += delta
            yield f"data: {json.dumps({'token': delta})}\n\n"

    state.seeker_messages.append({"role": "assistant", "content": full_text})

    conversation_ended = DONE_MARKER in full_text
    if conversation_ended:
        await _end_conversation(state)

    yield f"data: {json.dumps({'done': True, 'conversation_ended': conversation_ended})}\n\n"


# ── Endpoints ────────────────────────────────────────────────


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.server
    seeker_state = _load_seeker_state(state)
    has_q = _has_questions(state)
    return {
        "has_questions": has_q,
        "conversation_active": state.seeker_conversation_active,
        "questions_answered": not has_q and not state.seeker_conversation_active,
        "last_conversation_file": seeker_state.get("last_conversation_file"),
        "seeker_enabled": state.config.seeker_enabled,
    }


@router.get("/conversation")
async def get_conversation(request: Request):
    state = request.app.state.server

    if state.seeker_conversation_active:
        msgs = [m for m in state.seeker_messages if m["role"] in ("assistant", "user")]
        if msgs and msgs[0]["role"] == "user" and "ask me whatever" in msgs[0]["content"].lower():
            msgs = msgs[1:]
        return {"active": True, "messages": msgs}

    seeker_state = _load_seeker_state(state)
    last_file = seeker_state.get("last_conversation_file")
    if last_file:
        path = _conversations_dir(state) / last_file
        if path.exists():
            messages = _parse_conversation_markdown(path.read_text())
            return {"active": False, "messages": messages}

    return {"active": False, "messages": []}


@router.post("/start")
async def start_conversation(request: Request):
    state = request.app.state.server

    if state.seeker_conversation_active:
        return JSONResponse({"error": "Conversation already active"}, status_code=409)

    qp = _questions_path(state)
    if not qp.exists() or not qp.read_text().strip():
        return JSONResponse({"error": "No questions available"}, status_code=400)

    questions = qp.read_text()
    system_prompt = SYSTEM_PROMPT.format(questions=questions)
    state.seeker_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Go ahead \u2014 ask me whatever you'd like to know."},
    ]
    state.seeker_conversation_active = True

    return StreamingResponse(
        _stream_llm_response(state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class MessageBody(BaseModel):
    content: str


@router.post("/message")
async def send_message(body: MessageBody, request: Request):
    state = request.app.state.server

    if not state.seeker_conversation_active:
        return JSONResponse({"error": "No active conversation"}, status_code=409)

    if not body.content.strip():
        return JSONResponse({"error": "Message cannot be empty"}, status_code=400)

    state.seeker_messages.append({"role": "user", "content": body.content})

    return StreamingResponse(
        _stream_llm_response(state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/end")
async def end_conversation(request: Request):
    state = request.app.state.server

    if not state.seeker_conversation_active:
        return JSONResponse({"error": "No active conversation"}, status_code=409)

    await _end_conversation(state)
    return {"status": "ended"}


@router.get("/history")
async def list_conversations(request: Request):
    """Return a list of all past conversation files, newest first."""
    state = request.app.state.server
    conv_dir = _conversations_dir(state)
    if not conv_dir.exists():
        return []
    files = sorted(conv_dir.glob("conversation_*.md"), reverse=True)
    result = []
    for f in files:
        # Parse date from filename: conversation_YYYYMMDD_HHMMSS.md
        stem = f.stem.replace("conversation_", "")
        result.append({"filename": f.name, "date": stem})
    return result


@router.get("/history/{filename}")
async def get_past_conversation(filename: str, request: Request):
    """Return messages from a specific past conversation file."""
    state = request.app.state.server
    path = _conversations_dir(state) / filename
    if not path.exists() or not filename.startswith("conversation_"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    messages = _parse_conversation_markdown(path.read_text())
    return {"filename": filename, "messages": messages}
