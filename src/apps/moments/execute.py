"""Execute a moment task: run the agent, build an interface for the result."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent, DEFAULT_MODEL

STYLE_TEMPLATE_PATH = Path(__file__).resolve().parent / "style_template.html"

MAX_FILE_CHARS = 50_000
OUTPUT_FILES = ["index.html", "styles.css", "app.js", "data.js", "meta.json"]

INSTRUCTION_TEMPLATE = """You are a powerful AI agent executing a moment task for the user. You can:
- Search the web, fetch live data, and browse authenticated websites (Youtube, Google, Twitter/X, etc.)
- Read, write, and edit files on the user's machine
- Run shell commands, scripts, and git operations
- Do research and analysis on any topic
- Draft documents, build reports, generate charts
- Execute multi-step workflows end-to-end — actually DO the work, don't just describe it
- Spawn subagents to parallelize work across different data sources

Execute the task below by reading the relevant data, doing the actual work, and building \
an interface to present the results. You have complete creative freedom over the interface — \
use interactive JavaScript, charts, animations, tabs, accordions, whatever best serves the task. \
The only constraint is that the output must be a self-contained HTML file (all CSS/JS inline).

## Task

Focus on the "Specific Instructions for Agent" section below — that defines what to do. \
Treat other sections (Overview, Reasons, Implementation Notes) as background context only; \
do not present or reproduce them in your output.

{task_content}

## Available Data

The user's data is in `{logs_dir}/`. Only use sources relevant to the task above:

**Screen activity**: `session_*/labels.jsonl` — fields: text, start_time. Each session directory \
is a recording session. Ignore raw_events (mouse noise).

**Email**: `email/filtered.jsonl` — fields: subject, from, date, summary (nested under "source")
**Calendar**: `calendar/events.jsonl` — fields: summary, start, end, location, description (nested under "source")
**Notifications**: `notifications/filtered.jsonl` — fields: app, subtitle, body, summary (nested under "source")
**Filesystem changes**: `filesys/filtered.jsonl` — fields: type, path, summary (nested under "source")

Ignore internal files: checkpoints.jsonl, predictions.jsonl, metrics.jsonl, retriever*, raw_events*.

## Output

Your output is an INTERFACE, not a document. Do not write markdown or plain text — build an \
interactive HTML application. Think of it as a mini web app that lets the user explore and \
interact with the results.

Write these files to `{output_dir}/` (create the directory with `mkdir -p {output_dir}`):

1. **`{output_dir}/index.html`** — The main entry point. Keep this file small — it should load \
your CSS and JS from separate files. This renders in an iframe inside the PowerNap desktop app.

2. **`{output_dir}/styles.css`** — All CSS styles in a separate file. Link from index.html.

3. **`{output_dir}/app.js`** — All JavaScript in a separate file. Include from index.html. \
Put your data as a JSON object at the top of this file (e.g. `const DATA = [...]`), then the \
rendering logic below it.

4. **`{output_dir}/meta.json`** — Metadata:

**IMPORTANT: Split your output across these files.** Do NOT put everything in one giant index.html. \
Each file should be small enough to write in a single tool call. If your JS data is large, split \
it further (e.g. `data.js` for the data, `app.js` for the logic).

Be creative with the interface: interactive elements, visualizations, collapsible sections, \
search/filter, action buttons, tabs — whatever makes the result most useful. The reference \
palette below shows the app's colors — use as a starting point, not a cage.
```json
{{"title": "...", "description": "...", "completed_at": "<ISO 8601>", "frequency": "{frequency}", "schedule": "{schedule}"}}
```

## Reference Palette

{template}

## Writable directories

You can only write files to these locations (sandbox restriction):
- `{output_dir}/` — ALL your final output goes here (index.html, meta.json)
- `{logs_dir}/agent/` — scratch space for intermediate files (create with `mkdir -p {logs_dir}/agent/`)

You can read any file on the system, but writes elsewhere will fail. \
Do NOT write intermediate files to the output directory — use `{logs_dir}/agent/` for scratch work, \
then write only index.html and meta.json to `{output_dir}/`.

## How to work

Before diving in, plan your approach using PlanWrite to outline your steps and track progress.
Use subagents to parallelize and divide your work.

Use your tools as needed:
- **bash**: run shell commands to execute the task.
- **read_file**: read log files, task definitions, any file on the system.
- **write_file**: write your final index.html and meta.json to `{output_dir}/`.
- **subagent**: spawn subagents to research different aspects in parallel — e.g. one reads \
emails while another browses the web. Each subagent can focus on a piece and report back.
- **browser**: browse the web using browser_navigate, browser_read_text, browser_click, \
browser_type, and browser_screenshot. These use the user's Chrome cookies, so you can access \
their authenticated pages — Gmail, Google Calendar, GitHub, Slack, Twitter/X, Google Docs, etc.
- **web_search**: search the web for general information (Google-style queries).

**IMPORTANT: Use the browser (not web_search) for any site that requires authentication or has \
dynamic content** — Twitter/X, GitHub, Gmail, Slack, YouTube, Reddit, etc. web_search only returns \
public search snippets and cannot access logged-in pages or full page content. If you need to read \
a specific URL, tweet, thread, repo, or profile, use browser_navigate + browser_read_text.

For user-specific data (emails, calendar, notifications), prefer the local log files in \
`{logs_dir}/` first — they're faster than browsing. Use the browser when you need live or \
more detailed data that isn't in the logs.

## Execution

1. Plan with PlanWrite — break the task into steps.
2. Read the data sources relevant to this task, process them, and produce the result. Use subagents to parallelize.
3. Once the task is complete, design an interface that presents the result clearly.
4. Write index.html and meta.json to `{output_dir}/`.
"""


UPDATE_INSTRUCTION_TEMPLATE = """You are a powerful AI agent updating an existing moment interface with fresh data. You can:
- Search the web, fetch live data, and browse authenticated websites (Youtube, Google, Twitter/X, etc.)
- Read, write, and edit files on the user's machine
- Run shell commands, scripts, and git operations
- Do research and analysis on any topic
- Draft documents, build reports, generate charts
- Execute multi-step workflows end-to-end — actually DO the work, don't just describe it
- Spawn subagents to parallelize work across different data sources

This moment was previously generated and the interface already exists. Your job is to UPDATE it \
with fresh, current data — not rebuild it from scratch. Keep the existing design, layout, and \
interface structure. Focus on refreshing the content, data, and any time-sensitive information.

## Task

Focus on the "Specific Instructions for Agent" section below — that defines what to do. \
Treat other sections (Overview, Reasons, Implementation Notes) as background context only; \
do not present or reproduce them in your output.

{task_content}

## Existing Output

Here are the current files in the output directory. Preserve the interface design — update the \
data and content while keeping the same structure, styles, and interaction patterns. If the \
existing interface has issues or could be meaningfully improved, you may make targeted improvements, \
but do not redesign from scratch.

{existing_files}

## Available Data

The user's data is in `{logs_dir}/`. Only use sources relevant to the task above:

**Screen activity**: `session_*/labels.jsonl` — fields: text, start_time. Each session directory \
is a recording session. Ignore raw_events (mouse noise).

**Email**: `email/filtered.jsonl` — fields: subject, from, date, summary (nested under "source")
**Calendar**: `calendar/events.jsonl` — fields: summary, start, end, location, description (nested under "source")
**Notifications**: `notifications/filtered.jsonl` — fields: app, subtitle, body, summary (nested under "source")
**Filesystem changes**: `filesys/filtered.jsonl` — fields: type, path, summary (nested under "source")

Ignore internal files: checkpoints.jsonl, predictions.jsonl, metrics.jsonl, retriever*, raw_events*.

## Output

Write updated files to `{output_dir}/` — overwrite the existing files with refreshed versions.

1. **`{output_dir}/index.html`** — Keep the same structure. Update any dynamic content.

2. **`{output_dir}/styles.css`** — Keep existing styles unless there's a specific improvement to make.

3. **`{output_dir}/app.js`** — Update the data (the JSON object at the top) with fresh data. \
Keep the rendering logic unless there's a bug to fix or a clear improvement.

4. **`{output_dir}/meta.json`** — Metadata:
```json
{{"title": "...", "description": "...", "completed_at": "<ISO 8601>", "frequency": "{frequency}", "schedule": "{schedule}"}}
```

**IMPORTANT: Split your output across these files.** Do NOT put everything in one giant index.html. \
Each file should be small enough to write in a single tool call. If your JS data is large, split \
it further (e.g. `data.js` for the data, `app.js` for the logic).

## Reference Palette

{template}

## Writable directories

You can only write files to these locations (sandbox restriction):
- `{output_dir}/` — ALL your final output goes here (index.html, meta.json)
- `{logs_dir}/agent/` — scratch space for intermediate files (create with `mkdir -p {logs_dir}/agent/`)

You can read any file on the system, but writes elsewhere will fail. \
Do NOT write intermediate files to the output directory — use `{logs_dir}/agent/` for scratch work, \
then write only your output files to `{output_dir}/`.

## How to work

Before diving in, plan your approach using PlanWrite to outline your steps and track progress.
Use subagents to parallelize and divide your work.

Use your tools as needed:
- **bash**: run shell commands to execute the task.
- **read_file**: read log files, task definitions, any file on the system.
- **write_file**: write your updated files to `{output_dir}/`.
- **subagent**: spawn subagents to research different aspects in parallel — e.g. one reads \
emails while another browses the web. Each subagent can focus on a piece and report back.
- **browser**: browse the web using browser_navigate, browser_read_text, browser_click, \
browser_type, and browser_screenshot. These use the user's Chrome cookies, so you can access \
their authenticated pages — Gmail, Google Calendar, GitHub, Slack, Twitter/X, Google Docs, etc.
- **web_search**: search the web for general information (Google-style queries).

**IMPORTANT: Use the browser (not web_search) for any site that requires authentication or has \
dynamic content** — Twitter/X, GitHub, Gmail, Slack, YouTube, Reddit, etc. web_search only returns \
public search snippets and cannot access logged-in pages or full page content. If you need to read \
a specific URL, tweet, thread, repo, or profile, use browser_navigate + browser_read_text.

For user-specific data (emails, calendar, notifications), prefer the local log files in \
`{logs_dir}/` first — they're faster than browsing. Use the browser when you need live or \
more detailed data that isn't in the logs.

## Execution

1. Plan with PlanWrite — note what data needs refreshing vs. what to keep.
2. Read the fresh data sources relevant to this task. Use subagents to parallelize.
3. Compare fresh data with what's already in the existing interface.
4. Update the data/content while preserving the interface structure.
5. Write the updated files to `{output_dir}/`.
"""


def _read_existing_output(output_dir: str) -> dict[str, str]:
    """Read existing output files from a moment's output directory."""
    files = {}
    for name in OUTPUT_FILES:
        path = Path(output_dir) / name
        if path.exists():
            content = path.read_text()
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + f"\n[... truncated, {len(content)} chars total ...]"
            files[name] = content
    return files


def _format_existing_files(files: dict[str, str]) -> str:
    """Format existing output files as a prompt section."""
    sections = []
    for name, content in files.items():
        sections.append(f"### `{name}`\n```\n{content}\n```")
    return "\n\n".join(sections)


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}
    result = {}
    for line in content[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def run(
    task_path: str,
    output_dir: str,
    logs_dir: str,
    model: str = DEFAULT_MODEL,
    frequency_override: str | None = None,
    schedule_override: str | None = None,
) -> bool:
    """Execute a moment task. Returns True if index.html was produced."""
    task_content = Path(task_path).read_text()
    fm = _parse_frontmatter(task_content)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    effective_frequency = frequency_override or fm.get("frequency", "")
    effective_schedule = schedule_override or fm.get("schedule", "")

    template = STYLE_TEMPLATE_PATH.read_text() if STYLE_TEMPLATE_PATH.exists() else ""

    existing_index = Path(output_dir) / "index.html"
    if existing_index.exists():
        existing_files = _read_existing_output(output_dir)
        instruction = UPDATE_INSTRUCTION_TEMPLATE.format(
            task_content=task_content,
            output_dir=output_dir,
            logs_dir=logs_dir,
            frequency=effective_frequency,
            schedule=effective_schedule,
            template=template,
            existing_files=_format_existing_files(existing_files),
        )
    else:
        instruction = INSTRUCTION_TEMPLATE.format(
            task_content=task_content,
            output_dir=output_dir,
            logs_dir=logs_dir,
            frequency=effective_frequency,
            schedule=effective_schedule,
            template=template,
        )

    agent, _ = build_agent(model)
    agent.max_rounds = 100
    agent.run([{"role": "user", "content": instruction}])

    # Write meta.json as fallback if agent didn't
    meta_path = Path(output_dir) / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "title": fm.get("title", Path(task_path).stem),
            "description": fm.get("description", ""),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "frequency": effective_frequency,
            "schedule": effective_schedule,
        }, indent=2))

    return (Path(output_dir) / "index.html").exists()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute a moment task")
    parser.add_argument("task_path", help="Path to the task .md file")
    parser.add_argument("output_dir", help="Directory to write HTML output")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=os.environ.get("POWERNAP_AGENT_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    success = run(args.task_path, args.output_dir, args.logs_dir, model=args.model)
    print("Success" if success else "Failed")
