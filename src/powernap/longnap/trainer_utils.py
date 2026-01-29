"""
Message-based prompt utilities for the LongNAP trainer.

These functions return message dicts that can be appended to a conversation
and rendered by Qwen3VLRenderer.
"""

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

THINK_INSTRUCTION = (
    "Task: Predict the user's likely next steps.\n\n"
    "Look at the images and past actions. Consider:\n"
    "1) Person-based factors (traits, goals, preferences, habits, relationships, capabilities, etc.).\n"
    "2) Situation-based factors (constraints, incentives, risks, social norms, environment, time of day, etc.).\n\n"
    "Explain how person and situation-based factors contribute to the prediction, "
    "and how they interact to produce the likely next steps.\n\n"
    "Output ONLY your rationale wrapped by a <think>...</think> block."
)

REVISE_INSTRUCTION = (
    "Re-evaluate your reasoning using this context.\n\n"
    "Explain how person-based and situation-based factors contribute to the updated prediction, "
    "and how their interaction changes (or confirms) the likely next steps.\n\n"
    "Output ONLY your revised rationale wrapped by a <revise>...</revise> block."
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
        f"Output them ONLY as <action>...</action> tags inside <actions> block, "
        f"with each action wrapped in its own <action> tag."
    )
    return {
        "role": "user",
        "content": content,
    }
