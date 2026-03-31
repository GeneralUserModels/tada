"""Analyze user activity logs to discover agent automation opportunities."""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent, DEFAULT_MODEL

INSTRUCTION_TEMPLATE = """\
You are analyzing a user's digital activity logs to discover opportunities for an AI agent to augment their workflow.

The AI agent that will execute these tasks is powerful. It runs in the background and can:
- Search the web, monitor RSS/arxiv/Twitter feeds, and fetch live data
- Do research and analysis on topics of interest to the user
- Read, write, and edit files on the user's machine
- Draft emails, Slack messages, documents, and code
- Export charts, generate reports, build slide decks
- Execute multi-step workflows end-to-end (not just "suggest" — actually DO the thing)
- Maintain persistent context across runs (reading lists, experiment logs, etc.)

Your job is to predict WHAT to automate — not HOW. The executing agent is capable and will figure out \
implementation details on its own. Find high-value workflows where this agent can save real effort — \
especially multi-step sequences the user repeats manually, research and information foraging the agent \
can do proactively, and "extra-mile" tasks that would be valuable but the user never bothers doing \
themselves. Tasks do NOT need to span multiple apps — a single-app workflow that the agent can handle \
end-to-end is just as valuable.

## Log files to read (all in {logs_dir}/)

**PRIMARY — read these first, they are the most important:**
- session_*/labels.jsonl — the user's actual screen activity sessions. Fields: text, start_time. Read ALL session directories. Ignore raw_events (mouse noise). This is where the real workflow patterns live. Look for repeated multi-step sequences across sessions.

**SECONDARY — use these for additional context:**
- email/filtered.jsonl — fields: subject, from, date, summary (nested under "source")
- calendar/events.jsonl — fields: summary, start, end, location, description (nested under "source")
- notifications/filtered.jsonl — fields: app, subtitle, body, summary (nested under "source")
- filesys/filtered.jsonl — fields: type, path, summary (nested under "source")

**IGNORE these files — they are internal pipeline data, not user activity:**
- checkpoints.jsonl, predictions.jsonl, metrics.jsonl, retriever*, raw_events*

Start by reading ALL session_*/labels.jsonl files. These show what the user actually does on their computer. The other sources are supporting context — do not base tasks solely on emails/notifications.

## What to look for

Focus on the SESSION LOGS. Look for:
- **Multi-step manual workflows** — the same sequence of 3+ steps repeated across sessions. The task should collapse these into a single command.
- **Content production drudgery** — manually exporting, downloading, copying, and arranging artifacts. The agent should do the entire pipeline end-to-end.
- **Information foraging** — searching for, reading, and comparing information from multiple sources. The agent should do the research and present a structured summary.
- **Communication overhead** — triaging, classifying, and responding to messages. The agent should handle the routine parts, surface what needs human judgment, and prepare drafts the user can review and send in seconds.
- **Things the user SHOULD do but doesn't** — valuable habits (note-taking, tracking, summarizing) that the user skips. The agent can maintain these proactively.
- **Learning opportunities** — things the user is working with but could understand more deeply. The agent can teach concepts, explain techniques, surface relevant papers/talks, or create personalized explainers based on what the user is actually doing. Look for tools, libraries, domains, or patterns where a short educational deep-dive would level up the user's work.

## Quality bar for tasks

- A BAD task is vague, single-step, or just a notification. A GOOD task clearly describes what the user needs and why, grounded in observed behavior.
- Focus on the problem and desired outcome — don't prescribe implementation steps, the executing agent will figure those out.
- Tasks should be grounded in specific patterns you observed in the logs — not generic productivity advice.
- Do NOT produce pop-psychology insights like "user has anxiety about builds" or "user switches between deep work and dopamine hits." Focus on concrete workflows the agent can execute.

## How to work

Before diving in, plan your approach using PlanWrite to outline your steps. Use PlanUpdate to track progress as you go.

Use your tools aggressively:
- **bash**: run Python snippets to compute statistics (most frequent apps, common action sequences, time spent per app, repeated multi-step patterns). Don't just eyeball the logs — quantify.
- **read_file**: read all log files. Don't skip any session directories.
- **write_file**: write each task file individually. Do NOT write a Python script to generate task files — use the write_file tool directly for each one so you can craft the content carefully.
- **subagent**: spawn subagents to analyze different session directories or log sources in parallel. Each subagent can focus on a subset of sessions and report back observations. This is especially useful when there are many session_* directories.

### Workflow

1. **Check existing tasks**: First, check if {logs_dir}/tasks/ already has task files. If so, read them all to understand what's already been proposed. You must not duplicate existing tasks — only add new, different ones.
2. **Plan**: Use PlanWrite to outline your steps. List all session directories and log files you need to read.
3. **Read & analyze**: Read ALL log files. Use subagents to parallelize reading across session directories. Run bash commands with Python snippets to compute statistics. Reflect on what you find as you go.
4. **Write tasks**: Only AFTER completing steps 1-3, write the task files one at a time using write_file. Update your todos as you complete each file.

## Output
IMPORTANT: All output files MUST be written to {logs_dir}/tasks/. Create this directory first with bash, then use write_file to write each task file there. Write at least 20 markdown files (ideally more), one per discovered task.

Filename: slugified title + .md (e.g., wandb-experiment-monitoring.md)

Each file MUST start with this exact frontmatter format:
---
title: <title>
description: <one-line summary>
frequency: <daily|weekly|once>
schedule: <specify when e.g. "daily at 8am", "every Monday 9am", "once">
confidence: <0.0-1.0>
usefulness: <1-10>
---

After the frontmatter, write the rest of the file in whatever structure best fits the task. Describe \
what the user needs and the observed behavior that motivates it. Do NOT write implementation instructions \
for the executing agent — it will figure out how to do it. Every task MUST include a Reasons section \
citing specific patterns from the logs.

## Rules
- Every task MUST cite patterns observed in the logs (repeated workflows, app-switching sequences, recurring actions across sessions)
- Do NOT produce generic productivity advice — every task must be grounded in observed behavior
- Do NOT produce reactive or trigger-based tasks ("when X happens, do Y"). Every task must be \
something the agent can execute on a schedule — a batch of work it runs at a fixed time and \
produces a complete result. No continuous monitoring, no event listeners, no "watch for changes."
- confidence reflects how strongly the logs support this task existing
- usefulness reflects how much time/effort/value the automation would provide

When you are done, run `ls -la {logs_dir}/tasks/` to verify all task files exist and are non-empty. Read a few back to confirm they have real content, not placeholder text.
"""


def run(logs_dir: str, model: str = DEFAULT_MODEL) -> str:
    agent, _ = build_agent(model)
    agent.max_rounds = 200
    instruction = INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir)
    messages = [{"role": "user", "content": instruction}]
    return agent.run(messages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover agent tasks from activity logs")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("POWERNAP_AGENT_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    result = run(args.logs_dir, model=args.model)
    print(result)
