#!/usr/bin/env python3
"""
Test script for SleepWalk computer-use pipeline.

Feeds a list of high-level actions one by one to the LLM,
takes a fresh screenshot before each action, and executes the parsed steps.

Usage:
    python test_sleepwalk.py
    python test_sleepwalk.py --model gemini/gemini-2.5-flash-preview
    python test_sleepwalk.py --dry-run   # just print steps, don't execute
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import time

from litellm import completion as litellm_completion

from powernap.sleepwalk.computer import ComputerController
from powernap.sleepwalk.tools import make_messages, parse_steps, run_step, is_done


ACTIONS = [
    "Launch Chrome",
    "Click the Chrome address bar at the top of the browser",
    "Do a Google search for 'warriors'",
]


def main():
    parser = argparse.ArgumentParser(description="Test SleepWalk computer-use")
    parser.add_argument("--model", type=str, default="gemini/gemini-3-flash-preview")
    parser.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between actions")
    parser.add_argument("--max-iter", type=int, default=5, help="Max iterations per action")
    args = parser.parse_args()

    computer = ComputerController()

    print(f"Model: {args.model}")
    print(f"Actions: {len(ACTIONS)}")
    print(f"Delay between actions: {args.delay}s")
    print(f"Dry run: {args.dry_run}")
    print("Starting in 3 seconds...\n")
    time.sleep(3)

    for i, action in enumerate(ACTIONS, 1):
        print(f"\n{'='*60}")
        print(f"Action {i}/{len(ACTIONS)}: {action}")
        print(f"{'='*60}")

        for iteration in range(1, args.max_iter + 1):
            print(f"\n--- Iteration {iteration}/{args.max_iter} ---")

            # take screenshot
            print("[screenshot] capturing...")
            screenshot_b64, width, height = computer.screenshot()
            print(f"[screenshot] {width}x{height}")

            # build prompt and call LLM
            messages = make_messages(action, screenshot_b64)
            print(f"[llm] calling {args.model}...")
            t0 = time.time()
            response = litellm_completion(model=args.model, messages=messages)
            latency = time.time() - t0

            response_text = response.choices[0].message.content or ""
            print(f"[llm] response ({latency:.2f}s): {response_text[:300]}")

            # check for done
            if is_done(response_text):
                print(f"[done] action complete after {iteration} iteration(s)")
                break

            # parse
            steps = parse_steps(response_text)
            if not steps:
                print(f"[done] no steps parsed, treating as done")
                break

            step = steps[0]
            print(f"[parse] step: {step}")

            # execute
            if not args.dry_run:
                print("[execute] running...")
                run_step(step, computer)
                print("[execute] done")
            else:
                print("[execute] skipped (dry run)")

            time.sleep(0.5)
        else:
            print(f"[warn] max iterations ({args.max_iter}) reached for action")

        # wait for the action to settle
        time.sleep(args.delay)

    print(f"\n{'='*60}")
    print("All actions completed.")


if __name__ == "__main__":
    main()
