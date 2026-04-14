"""Analyze user activity logs to generate questions that build a richer user model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent

INSTRUCTION_TEMPLATE = """\
You are analyzing a user's digital activity logs to generate questions that will help build a richer model \
of who this person is — their beliefs, desires, intentions, emotional states, habits, values, and anything \
that surprises you about their behavior.

Your questions will be presented to the user in a conversation. Their answers will help AI systems \
(like task planners and automation agents) better predict what the user needs or might do next.

## Step 1: Read existing conversations

Check {logs_dir}/active-conversations/ for any existing files:
- **questions.md** — previously generated questions. Read it to avoid duplicates.
- **conversation_*.md** — past conversations with the user. Read ALL of them. These are gold — they \
tell you what the user has already shared about themselves. Use this to go deeper, not wider.

## Step 2: Read activity logs and user knowledge

Read activity from these files in {logs_dir}/:

**PRIMARY — these are the most important:**
- session_*/labels.jsonl — the user's actual screen activity. Fields: text, start_time. Read ALL \
session directories. Ignore raw_events (mouse noise).
- audio/filtered.jsonl — fields: text, timestamp, summary (nested under "source"). Transcribed audio \
from the user's microphone. This captures what the user says aloud — meetings, voice notes, \
conversations — and is uniquely revealing of beliefs, intentions, and affect.
- memory/ — a wiki of markdown pages about the user (people, projects, interests, habits, personality). \
Read memory/index.md for a catalog. Use this to understand what is already known about the user so \
your questions go deeper, not wider. Ask about things the wiki is uncertain or silent about.

**SECONDARY — use for additional context:**
- email/filtered.jsonl — fields: subject, from, date, summary (nested under "source")
- calendar/events.jsonl — fields: summary, start, end, location, description (nested under "source")
- notifications/filtered.jsonl — fields: app, subtitle, body, summary (nested under "source")
- filesys/filtered.jsonl — fields: type, path, summary (nested under "source")

**IGNORE these files — they are internal pipeline data, not user activity:**
- checkpoints.jsonl, predictions.jsonl, metrics.jsonl, retriever*, raw_events*

Use subagents to read session directories in parallel.

## Step 3: Reflect and generate questions

Generate 5-10 questions. Each question should:

1. **Be informed by observed behavior** — questions should emerge from what you saw in the logs, but \
you don't need to cite specific moments. Synthesize across sessions to form abstract questions about \
patterns, tendencies, and motivations. "You seem to context-switch a lot mid-task — is that deliberate \
or do you wish you could stay focused longer?" is good. "Do you like programming?" is too generic.

2. **Target one of these categories:**
   - **belief** — what the user thinks is true ("Do you think the current auth approach is the right one?")
   - **desire** — what the user wants ("What's driving the urgency on this branch?")
   - **intent** — plans or reasons behind actions ("Were you planning to share those logs or just debugging?")
   - **affect** — how the user feels ("How frustrated are you with this issue?")
   - **surprise** — things that surprised YOU ("You closed the PR review and switched to YouTube — deliberate break or lost focus?")
   - **habit** — recurring patterns ("I notice you always check Slack before deep work — intentional warm-up?")
   - **value** — what the user prioritizes ("You spent way more time reviewing others' code than writing your own — is thorough reviewing important to you?")

3. **Be answerable in 1-3 sentences** — one question, one thing. No compound questions.

4. **Be genuinely useful for prediction** — the answer should help anticipate what the user will do, \
need, or feel in the future. "What's your favorite color?" fails. "Are you planning to deploy by end of \
week?" passes.

5. **Not duplicate any existing question** from questions.md or previously asked in conversation files.

6. **Be conversational and direct** — these come from an AI that has been observing the user. \
Acknowledge that naturally. Don't be creepy, but don't pretend you haven't been watching.

## Output

Write the questions to {logs_dir}/active-conversations/questions.md using write_file.

Format:
```
# Questions

## [category] Question text here
Why: brief note on what pattern or observation led to this question (optional).

## [category] Another question

```

If questions.md already exists, APPEND your new questions to the end of the file. Do NOT overwrite \
existing questions. Use bash to append (e.g. echo or cat >>), or read the file first and write back \
the full contents plus your additions.

## How to work

1. Use PlanWrite to outline your steps.
2. Check for existing conversation files and questions.md.
3. Use subagents to read session directories and log files in parallel.
4. Reflect — what's interesting, surprising, or ambiguous about this user's behavior?
5. Draft questions, check against existing ones, write output.
"""


def run(logs_dir: str, model: str, api_key: str | None = None) -> str:
    logs_dir = str(Path(logs_dir).resolve())
    Path(logs_dir, "active-conversations").mkdir(parents=True, exist_ok=True)
    agent, _ = build_agent(model, data_dir=logs_dir, api_key=api_key)
    agent.max_rounds = 100
    instruction = INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir)
    messages = [{"role": "user", "content": instruction}]
    return agent.run(messages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze activity logs to generate user-understanding questions")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("TADA_AGENT_MODEL", "anthropic/claude-sonnet-4-6"))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
    print(result)
