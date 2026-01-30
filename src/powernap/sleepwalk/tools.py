"""Prompt, parse, and execute pipeline for SleepWalk."""

import json
import re
import time


SYSTEM_PROMPT = """\
You are a computer-use agent. You see a screenshot and are told an action to perform.

You will be called in a loop. Each call you get a fresh screenshot of the current screen state.
Output exactly ONE next step as a single JSON object.
If the action is already completed (you can see it succeeded in the screenshot), output exactly: DONE

Output ONLY a single JSON object OR the word DONE. No explanation, no markdown.

A step is a JSON object with an "action" key and action-specific fields:

  {"action": "left_click", "x": 100, "y": 200}
  {"action": "right_click", "x": 100, "y": 200}
  {"action": "double_click", "x": 100, "y": 200}
  {"action": "type_text", "text": "hello world"}
  {"action": "press_key", "key": "enter"}          — also supports combos: "ctrl+c", "cmd+s"
  {"action": "scroll", "x": 400, "y": 300, "dy": -3}  — negative dy = scroll down
  {"action": "mouse_move", "x": 100, "y": 200}

Coordinates are absolute pixels from top-left of the screen."""


def is_done(response_text):
    return response_text.strip().upper() == "DONE"


def make_messages(action_text, screenshot_b64):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Execute: {action_text}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                },
            ],
        },
    ]


def parse_steps(response_text):
    """Extract step(s) from the LLM response. Handles both [...] arrays and single {...} objects."""
    text = response_text.strip()
    # try JSON array first
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        return json.loads(match.group())
    # try single JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return [json.loads(match.group())]
    return []


def run_step(step, computer):
    """Execute a single parsed step dict using ComputerController."""
    action = step.get("action", "")
    print(f"[sleepwalk] step: {step}")

    if action == "left_click":
        computer.click(step["x"], step["y"])
    elif action == "right_click":
        computer.right_click(step["x"], step["y"])
    elif action == "double_click":
        computer.double_click(step["x"], step["y"])
    elif action == "type_text":
        computer.type_text(step["text"])
    elif action == "press_key":
        computer.press_key(step["key"])
    elif action == "scroll":
        computer.scroll(step["x"], step["y"], step.get("dx", 0), step.get("dy", 0))
    elif action == "mouse_move":
        computer.mouse_move(step["x"], step["y"])
    else:
        print(f"[sleepwalk] unknown action: {action}")


def run_steps(steps, computer):
    """Execute a list of parsed step dicts using ComputerController."""
    for step in steps:
        run_step(step, computer)
        time.sleep(0.15)
