"""Analyze user activity logs to discover one-off tasks the agent can help with right now."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent, DEFAULT_MODEL

INSTRUCTION_TEMPLATE = """\
You are analyzing a user's digital activity logs to discover one-off tasks that an AI agent can help with RIGHT NOW.

Your job is to predict WHAT to automate — not HOW. The executing agent is capable and will figure out \
implementation details on its own.

Unlike recurring automation tasks, these are situational — things the user is currently working on, researching, or planning where the agent can jump in and produce something useful in a single run. Tasks should be informational only (research, summaries, drafts, context) — never instrumental actions that change the user's state.

The AI agent that will execute these tasks can:
- Search the web and fetch live data
- Browse authenticated websites (GitHub, Gmail, Twitter/X, YouTube, Slack, Google Docs, etc.) using the user's Chrome cookies
- Read, write, and edit files on the user's machine
- Run shell commands, scripts, git operations
- Do research, compile summaries, draft documents
- Execute multi-step workflows end-to-end

## Log files to read (all in {logs_dir}/)

**PRIMARY — read these first, they are the most important:**
- session_*/labels.jsonl — the user's actual screen activity sessions. Fields: text, start_time. Read ALL session directories. Ignore raw_events (mouse noise). This is where you'll find what the user is currently doing.

**SECONDARY — use these for additional context:**
- email/filtered.jsonl — fields: subject, from, date, summary (nested under "source")
- calendar/events.jsonl — fields: summary, start, end, location, description (nested under "source")
- notifications/filtered.jsonl — fields: app, subtitle, body, summary (nested under "source")
- filesys/filtered.jsonl — fields: type, path, summary (nested under "source")

**IGNORE these files — they are internal pipeline data, not user activity:**
- checkpoints.jsonl, predictions.jsonl, metrics.jsonl, retriever*, raw_events*

## What to look for

Focus on what the user is CURRENTLY doing or interested in. Look for:
- **Active research** — the user is searching for, reading about, or comparing something specific. The agent can do deeper research and compile a structured summary.
- **Planning or decision-making** — the user is planning a trip, evaluating options, comparing products, etc. The agent can gather more information, build a comparison, or draft an itinerary.
- **Unfinished work** — something the user started but hasn't completed. The agent can pick it up and finish it or prepare a draft.
- **Draft responses** — emails, Slack messages, or PR reviews the user needs to reply to. The agent can prepare draft responses the user can review and send in seconds instead of writing from scratch.
- **Information the user needs** — based on upcoming calendar events, recent emails, or notifications, what context or preparation would be helpful?
- **Content the user is consuming** — videos watched, articles read, threads followed. The agent can summarize, extract key points, or find related resources.
- **Learning opportunities** — things the user is working with but could understand more deeply. The agent can teach concepts, explain techniques, surface relevant papers/talks, or create personalized explainers based on what the user is actually doing right now.

## Quality bar

- Every task MUST be grounded in specific activity observed in the logs — not generic advice.
- Each task should produce a concrete artifact (summary, analysis, draft, comparison, report).
- Tasks should be specific enough that an agent can execute them without further clarification.
- Do NOT produce fluffy or vague tasks. "Help user be more productive" is garbage. "Research the top 5 restaurants near [location from calendar event]" is good.
- Do NOT produce tasks that are really recurring automations — those belong in discover.py.

## How to work

Use your tools aggressively:
- **subagent**: spawn subagents to read different session directories or log sources in parallel. This is essential — do not read all sessions yourself.
- **read_file**: read log files directly when needed.
- **bash**: run Python snippets to extract specific data points from logs.
- **write_file**: write each task file individually.

### Workflow

1. **Plan**: Use PlanWrite to outline your approach and steps.
2. **Read & analyze**: Use subagents to read ALL session_*/labels.jsonl files in parallel. Also read email, calendar, notifications, and filesys logs.
3. **Identify opportunities**: Based on what you find, identify specific one-off tasks where the agent can help right now.
4. **Write tasks**: Write each task file using write_file.

## Output

All output files MUST be written to {logs_dir}/oneoffs/. Create this directory first, then use write_file to write each task file there.

Filename: slugified title + .md (e.g., carmel-trip-research.md)

Each file MUST start with this exact frontmatter format:
---
title: <title>
description: <one-line summary of what the agent should do>
frequency: once
confidence: <0.0-1.0, how strongly the logs support that the user needs this>
usefulness: <1-10, how valuable the output would be>
---

After the frontmatter, include:
- What you observed in the logs that motivates this task
- What the user needs and why — do NOT write implementation instructions for the executing agent, it will figure out how to do it

## Rules
- Every task MUST cite specific activity from the logs
- Do NOT produce generic advice or recurring automation ideas
- confidence reflects how clearly the logs show the user needs this
- usefulness reflects how valuable the one-time output would be
- Focus on recency — what is the user doing NOW or in the last few sessions?

When you are done, run `ls -la {logs_dir}/oneoffs/` to verify all task files exist and are non-empty.
"""


def run(logs_dir: str, model: str = DEFAULT_MODEL) -> str:
    logs_dir = str(Path(logs_dir).resolve())
    Path(logs_dir, "oneoffs").mkdir(parents=True, exist_ok=True)
    agent, _ = build_agent(model)
    agent.max_rounds = 200
    instruction = INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir)
    messages = [{"role": "user", "content": instruction}]
    return agent.run(messages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover one-off tasks from activity logs")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("POWERNAP_AGENT_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
    print(result)
