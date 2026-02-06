import logging
import re
import time
import threading

from litellm import completion as litellm_completion

logger = logging.getLogger(__name__)

from powernap.sleepwalk.computer import ComputerController
from powernap.sleepwalk.tools import make_messages, parse_steps, run_step, is_done


def parse_actions(text):
    """Extract individual action strings from <action>...</action> tags."""
    actions = re.findall(r"<action>(.*?)</action>", text, re.DOTALL)
    if actions:
        return [a.strip() for a in actions if a.strip()]
    clean = re.sub(r"<[^>]+>", "", text).strip()
    return [clean] if clean else []


class SleepWalker:

    def __init__(self, model, inference_buffer, overlay, max_iterations=5):
        self.model = model
        self.inference_buffer = inference_buffer
        self.overlay = overlay
        self.max_iterations = max_iterations
        self.computer = ComputerController()
        self.active = threading.Event()
        self.latest_prediction = None  # set by inference thread: {"actions": "...", "seq": int}

    def run(self):
        """Main loop — runs on a dedicated daemon thread."""
        while True:
            self.active.wait()
            self._execute_loop()

    def _execute_loop(self):
        last_seq = -1

        while self.active.is_set():
            pred = self.latest_prediction
            if pred is None or pred["seq"] <= last_seq:
                time.sleep(0.5)
                continue

            last_seq = pred["seq"]

            # parse first action from the latest prediction
            actions = parse_actions(pred["actions"])
            if not actions:
                continue
            action = actions[0]

            print(f"[sleepwalk] executing: {action}")
            if self.overlay:
                self.overlay.update_sleepwalk(action, active=True)

            # execute the action
            self._execute_action(action)

            # wait for the inference buffer to grow
            # (the executed action gets captured -> labeled -> appended)
            buf_len = len(self.inference_buffer)
            while len(self.inference_buffer) <= buf_len and self.active.is_set():
                time.sleep(0.5)

        print("[sleepwalk] deactivated")

    def _execute_action(self, action_text):
        """Loop: screenshot → LLM → one step or DONE → repeat until done."""
        for i in range(self.max_iterations):
            screenshot_b64, width, height = self.computer.screenshot()
            messages = make_messages(action_text, screenshot_b64)

            print(f"[sleepwalk] iteration {i + 1}/{self.max_iterations}, calling {self.model}")
            while True:
                try:
                    response = litellm_completion(model=self.model, messages=messages)
                    break
                except Exception as e:
                    logger.warning(f"Sleepwalk LLM call failed: {e}. Retrying in 120s...")
                    time.sleep(120)

            response_text = response.choices[0].message.content or ""
            print(f"[sleepwalk] response: {response_text[:500]}")

            if is_done(response_text):
                print(f"[sleepwalk] action done after {i + 1} iteration(s)")
                return

            steps = parse_steps(response_text)
            if not steps:
                print(f"[sleepwalk] no steps parsed, treating as done")
                return

            run_step(steps[0], self.computer)
            time.sleep(0.5)

        print(f"[sleepwalk] max iterations ({self.max_iterations}) reached")
