"""Analyze user activity logs to discover agent automation opportunities."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint, sessions_with_new_content
from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model

INSTRUCTION_TEMPLATE = """\
You are analyzing a user's digital activity logs to discover opportunities for an AI agent to augment their workflow.

The AI agent that will execute these tasks is powerful. It runs in the background and can:
- Search the web, crawl pages, monitor RSS/arxiv/Twitter feeds, and fetch live data
- Browse authenticated websites (GitHub, Gmail, Twitter/X, YouTube, Slack, Google Docs, etc.) using the user's Chrome cookies
- Do deep research and analysis — read papers, compare approaches, synthesize across dozens of sources
- Read files on the user's machine for context
- Run shell commands, scripts, git operations, Python/Node code
- Pre-draft emails, Slack messages, documents, and code for the user to review
- Generate reports, build slide decks, create static HTML interfaces to present results
- Spawn subagents to parallelize work across different data sources
- Maintain persistent context across runs (reading lists, experiment logs, etc.)

The agent CANNOT: call LLMs at runtime in its output, modify arbitrary files on the user's machine, \
or build interactive interfaces that require a backend. It produces static artifacts (HTML, markdown, \
drafts) that the user reviews.

Your job is to predict WHAT to automate — not HOW. The executing agent is capable and will figure out \
implementation details on its own.

**Prioritize tasks that amplify the user's abilities:**
- **Information foraging and synthesis** — the agent's biggest advantage is reading, comparing, and \
synthesizing across many sources faster than any human. Prioritize tasks where the agent does deep \
research the user wouldn't have time for: surveying a field, comparing tools/approaches, reading \
papers/docs, compiling structured knowledge.
- **Complex multi-step workflows** — prefer ambitious tasks that chain together many operations. \
The agent thrives on tasks that are too tedious or time-consuming for a human to bother with.
- **"Extra-mile" tasks** — things that would be valuable but the user never gets around to doing. \
The agent can maintain habits, track things, produce summaries, and do prep work proactively.

Tasks do NOT need to span multiple apps — a single-app workflow that the agent can handle \
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
IMPORTANT: All output files MUST be written to {logs_dir}/tasks/. Create this directory first with bash, then use write_file to write each task file there. Write one markdown file per discovered task.

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
- Do NOT delete any existing files, tasks, or data

### Existing tasks:
Read ALL existing task files in {logs_dir}/tasks/ — you must not duplicate any existing task. Your job \
is to find NEW tasks that aren't already covered. If a new session reveals a variation or extension \
of an existing task, note that in a new task file rather than modifying the existing one.

When you are done, run `ls -la {logs_dir}/tasks/` to verify all task files exist and are non-empty. Read a few back to confirm they have real content, not placeholder text.
"""


INCREMENTAL_SECTION = """\

## Incremental Discovery

This is a RE-RUN. The last discovery was on **{last_discovery_date}**. Prioritize labels with \
`start_time` after this date, but analyze ALL sessions thoroughly.

### Sessions with new content since last discovery:
{sessions_with_new_content_list}

"""


def run(logs_dir: str, model: str, api_key: str | None = None) -> str:
    logs_path = Path(logs_dir).resolve()
    logs_dir = str(logs_path)
    checkpoint_path = logs_path / "tasks" / ".last_discovery"

    last_discovery = read_checkpoint(checkpoint_path)
    new_content_sessions = sessions_with_new_content(logs_dir, last_discovery)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(logs_dir=logs_dir)

    if last_discovery is not None and new_content_sessions:
        sessions_list = "\n".join(f"- {s}/labels.jsonl" for s in new_content_sessions)
        instruction += INCREMENTAL_SECTION.format(
            last_discovery_date=last_discovery.strftime("%Y-%m-%d %H:%M"),
            sessions_with_new_content_list=sessions_list,
        )
    elif last_discovery is not None and not new_content_sessions:
        instruction += (
            f"\n\n## Note\n\nThe last discovery was on "
            f"**{last_discovery.strftime('%Y-%m-%d %H:%M')}** and there are no new labels "
            f"in any session since then. Analyze all existing sessions and non-session logs "
            f"(email, calendar, notifications, filesystem) thoroughly for tasks that may "
            f"have been missed."
        )

    agent, _ = build_agent(model, logs_dir, api_key=api_key)
    agent.max_rounds = 200
    messages = [{"role": "user", "content": instruction}]
    result = agent.run(messages)

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover agent tasks from activity logs")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    model = args.model or resolve_moments_model()

    result = run(args.logs_dir, model=model, api_key=resolve_moments_api_key())
    print(result)
