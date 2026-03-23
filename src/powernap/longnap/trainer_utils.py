"""
Message-based prompt utilities for the LongNAP trainer.

These functions return message dicts that can be appended to a conversation
and rendered by Qwen3VLRenderer.
"""

from datetime import datetime
from typing import Dict, List, Any, Optional


TASK_DESCRIPTION = (
    "You will analyze user behavior and predict what the user will do next. "
    "Below are the actions the user took."
)

TASK_DESCRIPTION_WITH_IMAGES = (
    "You will analyze user behavior and predict what the user will do next. "
    "Below are the actions the user took. "
    "Look at the images of their device to help you predict the user's next action."
)

TASK_DESCRIPTION_MIXED = (
    "You will analyze user behavior and predict what the user will do next. "
    "Below is a chronological log of what the user has been doing, including "
    "screen activity and other context (emails, notifications, calendar events, files)."
)

THINK_INSTRUCTION = (
    "Task: Predict the user's likely next steps.\n\n"
    "Look at the images and past actions. Think about what the user is likely to do next.\n\n"
    "Output ONLY a <rationale>...</rationale> block with your rationale."
)

REVISE_INSTRUCTION = (
    "Re-evaluate your rationale using this context.\n\n"
    "Consider how this context changes (or confirms) the likely next steps.\n\n"
    "Output ONLY a <revise>...</revise> block with your final, revised rationale."
)


def build_context_block(events: List[Dict[str, Any]]) -> str:
    """Format a unified context buffer into a timestamped block.

    Each event must have: timestamp (float), text (str), source (str).
    Output format per line: [HH:MM] [source] text
    """
    sorted_events = sorted(events, key=lambda e: e["timestamp"])
    return "\n".join(
        f"[{datetime.fromtimestamp(e['timestamp']).strftime('%H:%M')}] [{e['source']}] {e['text']}"
        for e in sorted_events
    )


def fmt_action(text: str) -> str:
    return f"<action>{text}</action>"

def build_actions_block(records: List[Dict[str, Any]]) -> str:
    lines = [fmt_action(r["text"]) for r in records]
    return "<actions>\n" + "\n".join("    " + a for a in lines) + "\n</actions>"

def build_think_user_message() -> Dict[str, str]:
    """
    Build the user message that instructs the model to think about the prediction.
    
    Returns:
        A message dict with role='user' and the think instruction.
    """
    return {
        "role": "user",
        "content": THINK_INSTRUCTION,
    }


def build_revise_user_message(retrieved_text: Optional[str] = None) -> Dict[str, str]:
    """
    Build the user message that provides retrieved context and asks for revision.
    
    Args:
        retrieved_text: The retrieved context to include, or None if no context.
    
    Returns:
        A message dict with role='user' and the revise instruction.
    """
    context_block = retrieved_text if retrieved_text else "- (none)"
    content = (
        f"Here is additional context that may be relevant to the user's next steps:\n\n"
        f"{context_block}\n\n"
        f"{REVISE_INSTRUCTION}"
    )
    return {
        "role": "user",
        "content": content,
    }


def build_actions_user_message(future_len: int) -> Dict[str, str]:
    """
    Build the user message that asks for action predictions.
    
    Args:
        future_len: Number of actions to predict.
    
    Returns:
        A message dict with role='user' and the actions instruction.
    """
    content = (
        f"Now, using your claims, generate exactly {future_len} next actions the user will take.\n"
        f"Output ONLY <action>...</action> tags inside a larger <actions>...</actions> block, "
        f"with each action wrapped in its own <action> tag."
    )
    return {
        "role": "user",
        "content": content,
    }
