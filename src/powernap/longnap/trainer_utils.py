import torch


TASK_DESCRIPTION = (
    "You will analyze user behavior and predict what the user will do next. "
    "Below are the actions the user took."
)

TASK_DESCRIPTION_WITH_IMAGES = (
    "You will analyze user behavior and predict what the user will do next. "
    "Below are the actions the user took. "
    "Look at the images of their device to help you predict the user's next action."
)


def fmt_action(text):
    return f"<action>{text}</action>"


def build_actions_block(records):
    lines = [fmt_action(r["text"]) for r in records]
    return "<actions>\n" + "\n".join("    " + a for a in lines) + "\n</actions>"


def build_retrieve_prompt(base_ctx: str) -> str:
    head, sep, tail = base_ctx.rpartition("<|im_end|>")
    base_ctx = (head + tail).strip()
    return (
        f"{base_ctx}\n"
        "Task: Predict the user’s likely next steps.\n\n"
        "Look at the images and past actions. Consider:\n"
        "1) Person-based factors (traits, goals, preferences, habits, relationships, capabilities, etc.).\n"
        "2) Situation-based factors (constraints, incentives, risks, social norms, environment, time of day, etc.).\n\n"
        "Explain how person and situation-based factors contribute to the prediction, "
        "and how they interact to produce the likely next steps.\n\n"
        "Output your rationale inside a <think> block.<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n"
    )


def build_revise_prompt(think_block: str, retrieved_txt: str) -> str:
    return (
        f"{think_block}<|im_end|>\n<|im_start|>user\n"
        "Here is additional context that may be relevant to the user's next steps:\n\n"
        f"{retrieved_txt or '- (none)'}\n\n"
        "Re-evaluate your reasoning using this context.\n\n"
        "Explain how person-based and situation-based factors contribute to the updated prediction, "
        "and how their interaction changes (or confirms) the likely next steps.\n\n"
        "Output your revised rationale inside a <revise> block.<|im_end|>\n"
        "<|im_start|>assistant\n<revise>\n"
    )


def build_actions_prompt(revise_block: str, future_len: int) -> str:
    return (
        f"{revise_block}<|im_end|>\n<|im_start|>user\n"
        f"Now, using your claims, generate exactly {future_len} next actions the user will take.\n"
        f"Output them ONLY as <action>...</action> tags inside <actions> block, "
        f"with each action wrapped in its own <action> tag.<|im_end|>\n"
        f"<|im_start|>assistant\n<actions>\n"
    )

