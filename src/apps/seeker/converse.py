"""Multi-turn conversation with the user based on seeker questions."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from chat import ChatAgent, ChatSession
from server.config import DEFAULT_AGENT_MODEL

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "conversation.txt").read_text()

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

    agent = ChatAgent(model=model, system_prompt=SYSTEM_PROMPT.format(questions=questions))
    session = ChatSession(
        agent=agent,
        done_marker=DONE_MARKER,
        initial_user_message="Go ahead — ask me whatever you'd like to know.",
    )

    print("Starting conversation (type 'q' to quit early)\n")

    while session.active:
        response = session.respond()
        print(f"\n{session.display_text(response)}\n")

        if session.ended:
            break

        try:
            user_input = input("\033[36myou >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.strip().lower() in ("q", "quit", "exit"):
            break

        session.add_user_message(user_input)

    # Save conversation
    timestamp = datetime.now().strftime("%Y%m%d")
    output_path = conversations_dir / f"conversation_{timestamp}.md"
    session.save(output_path, assistant_label="Seeker")
    print(f"\nConversation saved to {output_path}")
    return str(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conversational seeker — ask questions to understand the user")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("TADA_AGENT_MODEL", DEFAULT_AGENT_MODEL))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
