"""Multi-turn conversation with the user based on seeker questions."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import litellm

from server.config import DEFAULT_AGENT_MODEL

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


def run(logs_dir: str, model: str = DEFAULT_AGENT_MODEL) -> str:
    logs_dir = str(Path(logs_dir).resolve())
    conversations_dir = Path(logs_dir, "active-conversations")
    conversations_dir.mkdir(parents=True, exist_ok=True)

    questions_path = conversations_dir / "questions.md"
    if not questions_path.exists():
        return "No questions.md found. Run seek.py first to generate questions."

    questions = questions_path.read_text()
    if not questions.strip():
        return "questions.md is empty. Run seek.py first to generate questions."

    system_prompt = SYSTEM_PROMPT.format(questions=questions)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Go ahead — ask me whatever you'd like to know."},
    ]

    print("Starting conversation (type 'q' to quit early)\n")

    while True:
        response = litellm.completion(model=model, messages=messages)
        assistant_text = response.choices[0].message.content

        done = DONE_MARKER in assistant_text
        display_text = assistant_text.replace(DONE_MARKER, "").strip()
        print(f"\n{display_text}\n")

        messages.append({"role": "assistant", "content": assistant_text})

        if done:
            break

        try:
            user_input = input("\033[36myou >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.strip().lower() in ("q", "quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})

    # Save conversation
    timestamp = datetime.now().strftime("%Y%m%d")
    output_path = conversations_dir / f"conversation_{timestamp}.md"

    # Build markdown from the conversation
    lines = ["# Conversation\n"]
    for msg in messages:
        if msg["role"] == "system":
            continue
        if msg["role"] == "assistant":
            text = msg["content"].replace(DONE_MARKER, "").strip()
            lines.append(f"**Seeker:** {text}\n")
        else:
            lines.append(f"**User:** {msg['content']}\n")

    output_path.write_text("\n".join(lines))
    print(f"\nConversation saved to {output_path}")
    return str(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conversational seeker — ask questions to understand the user")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("TADA_AGENT_MODEL", DEFAULT_AGENT_MODEL))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
