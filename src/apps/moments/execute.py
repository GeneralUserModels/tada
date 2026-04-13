"""Execute a moment task: run the agent, build an interface for the result."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model
from apps.moments.verify_refine import verify_and_refine

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

OUTPUT_FILES = ["index.html", "styles.css", "app.js", "data.js", "base.css", "components.js", "meta.json"]

INSTRUCTION_TEMPLATE = """You are a powerful AI agent executing a moment task for the user. You can:
- Search the web, fetch live data, and browse authenticated websites (Youtube, Google, Twitter/X, etc.)
- Read, write, and edit files on the user's machine
- Run shell commands, scripts, and git operations
- Do research and analysis on any topic
- Draft documents, build reports, generate charts
- Execute multi-step workflows end-to-end — actually DO the work, don't just describe it
- Spawn subagents to parallelize work across different data sources

Execute the task below by reading the relevant data, doing the actual work, and building \
an interface to present the results.

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
your CSS and JS from separate files. This renders in an iframe inside the Tada desktop app.

2. **`{output_dir}/styles.css`** — All CSS styles in a separate file. Link from index.html.

3. **`{output_dir}/app.js`** — All JavaScript in a separate file. Include from index.html. \
Put your data as a JSON object at the top of this file (e.g. `const DATA = [...]`), then the \
rendering logic below it. Remember: app.js shares global scope with components.js, so only \
declare NEW identifiers — never redeclare anything components.js already provides.

4. **`{output_dir}/meta.json`** — Metadata:
```json
{{"title": "...", "description": "...", "completed_at": "<ISO 8601>", "frequency": "{frequency}", "schedule": "{schedule}"}}
```

**IMPORTANT: Split your output across these files.** Do NOT put everything in one giant index.html. \
Each file should be small enough to write in a single tool call. If your JS data is large, split \
it further (e.g. `data.js` for the data, `app.js` for the logic).

## Templates & Component Library

Templates are at `{templates_dir}/`. Each template is a React 18 app (index.html + styles.css + \
app.js) with placeholder data. Each template has a **README.md** documenting its DATA schema, \
components used, and template-specific components. Read the README first with \
`cat {templates_dir}/<name>/README.md`.

**Shared resources** at `{templates_dir}/shared/`:
- **base.css** — Full design system (colors, glass cards, badges, stats, typography, animations)
- **components.js** — Reusable React component library on the `PN` namespace
- **README.md** — Full API docs for all shared components

**CRITICAL — global scope rules:** All `<script>` tags in index.html share ONE global scope. \
components.js runs first and declares `h`, `useState`, `useCallback`, `useMemo`, `useEffect`, \
and every component function (`PageHeader`, `GlassCard`, `Badge`, etc.) as globals. \
Your app.js MUST NOT use `const`, `let`, or `var` to redeclare ANY identifier that components.js \
already defines — this causes `SyntaxError: Identifier has already been declared` and the app \
will not render. Just reference them directly (e.g. `h(PageHeader, ...)` not `const PageHeader = ...`).

**Available components** (already global from components.js — use directly, no import needed):
- `PageHeader` — title, subtitle, optional badges and status badge
- `GlassCard` — frosted glass container with optional animation delay
- `Badge` / `BadgeRow` — pill labels (success/warning/danger variants)
- `StatRow` — horizontal metrics row with stat pills
- `SearchInput` — controlled search input field
- `FilterBar` — pill-style filter buttons with active state
- `TabBar` — tab navigation with optional counts
- `ItemCard` — content card with title, description, badges, meta
- `EmptyState` — placeholder message
- `ResultCount` — item/row count display
- `useFilter` / `useSearch` — filtering and search hooks

**Available templates:**
- **dashboard** — Stats + filterable/searchable card grid. For: metrics, tracking, status overviews.
- **feed** — Tabbed content stream with scores. For: articles, alerts, research papers.
- **report** — Collapsible sections, timeline, action items. For: summaries, recaps, advisories.
- **table** — Sortable/filterable data table with expandable rows. For: structured data, logs.
- **blank** — Minimal scaffold. For: anything custom.

**How to use templates:**
1. Read the template's README.md and app.js to understand the DATA schema and components.
2. Copy the template files to your output dir: index.html, styles.css, app.js.
3. Also copy `{templates_dir}/shared/base.css` and `{templates_dir}/shared/components.js` \
to `{output_dir}/` as sibling files.
4. Update the paths in index.html: change `../shared/base.css` to `base.css` and \
`../shared/components.js` to `components.js`.
5. Replace the DATA object with your real data.

**Reuse from existing moments:** Browse `{output_dir}/../` to see previously generated moments. \
If another moment has a useful component (chart, timeline, custom card layout), copy and adapt it \
into your output. The component ecosystem grows over time.

**Create new reusable components:** When building something novel, implement clean React components \
with clear props (using `h()` which is already `React.createElement`). Define them at the top of \
app.js using `function MyComponent(...)` syntax (NOT `const MyComponent = ...`) so they \
can be borrowed by future moments. Think of each new component as a potential addition to the library.

You have full creative freedom to modify templates, combine elements from multiple templates, \
or build entirely new interfaces. The only requirement is that your output uses the same design \
language (colors, glass cards, typography, radii) so it feels native to Tada. Use \
`{templates_dir}/shared/base.css` as the canonical design system reference.

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
2. Read `{templates_dir}/shared/README.md` to understand the shared component API, then read \
the README.md of the template that best fits your task.
3. Read the data sources relevant to this task, process them, and produce the result. Use subagents to parallelize.
4. Build the interface by composing from shared `PN.*` components and template-specific components. \
Also browse `{output_dir}/../` for reusable components from other moments.
5. Write your output files to `{output_dir}/` (including base.css and components.js).
6. **Verify your JS**: run `node --check {output_dir}/app.js` (and any other .js files you wrote) \
to catch syntax errors. Fix any errors before finishing.
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

The current interface files are at `{output_dir}/`. Read them with your tools to understand \
the existing design, layout, and data structure. Preserve the interface design — update the \
data and content while keeping the same structure, styles, and interaction patterns. If the \
existing interface has issues or could be meaningfully improved, you may make targeted improvements, \
but do not redesign from scratch.

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
6. **Verify your JS**: run `node --check {output_dir}/app.js` (and any other .js files you wrote) \
to catch syntax errors. Fix any errors before finishing.
"""



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


def _check_js_compilation(output_dir: str) -> bool:
    """Run node --check on all .js files in output_dir. Returns True if all pass."""
    for js_file in sorted(Path(output_dir).glob("*.js")):
        result = subprocess.run(
            ["node", "--check", str(js_file)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  [compile] FAILED: {js_file.name}: {result.stderr.strip()}")
            return False
    return True


def _restore_backup(backup_dir: str, output_dir: str) -> None:
    """Replace output_dir contents with backup."""
    print(f"  [safety] restoring previous version from backup")
    shutil.rmtree(output_dir)
    shutil.move(backup_dir, output_dir)


def _clean_output(output_dir: str) -> None:
    """Remove all files from output_dir (first-ever run failed)."""
    print(f"  [safety] removing failed output (no previous version)")
    shutil.rmtree(output_dir)


def _cleanup_backup(backup_dir: str) -> None:
    """Remove backup after successful compilation."""
    if Path(backup_dir).exists():
        shutil.rmtree(backup_dir)


def run(
    task_path: str,
    output_dir: str,
    logs_dir: str,
    model: str,
    frequency_override: str | None = None,
    schedule_override: str | None = None,
    api_key: str | None = None,
) -> bool:
    """Execute a moment task. Returns True if index.html was produced."""
    task_content = Path(task_path).read_text()
    fm = _parse_frontmatter(task_content)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Back up existing output so we can restore on failure
    backup_dir = str(Path(output_dir).parent / "_backups" / Path(output_dir).name)
    had_previous = (Path(output_dir) / "index.html").exists()
    if had_previous:
        if Path(backup_dir).exists():
            shutil.rmtree(backup_dir)
        Path(backup_dir).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output_dir, backup_dir)

    effective_frequency = frequency_override or fm.get("frequency", "")
    effective_schedule = schedule_override or fm.get("schedule", "")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing_index = Path(output_dir) / "index.html"
    if existing_index.exists():
        instruction = f"Current date and time: **{now}**\n\n" + UPDATE_INSTRUCTION_TEMPLATE.format(
            task_content=task_content,
            output_dir=output_dir,
            logs_dir=logs_dir,
            frequency=effective_frequency,
            schedule=effective_schedule,
        )
    else:
        instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(
            task_content=task_content,
            output_dir=output_dir,
            logs_dir=logs_dir,
            frequency=effective_frequency,
            schedule=effective_schedule,
            templates_dir=str(TEMPLATES_DIR),
        )

    agent, _ = build_agent(model, logs_dir, extra_write_dirs=[output_dir], api_key=api_key)
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

    # Check if execute produced a valid output before running verify_and_refine
    execute_ok = (Path(output_dir) / "index.html").exists() and _check_js_compilation(output_dir)

    if execute_ok:
        # Snapshot post-execute state so we can recover if verify_and_refine breaks it
        pre_refine_dir = str(Path(output_dir).parent / "_pre_refine" / Path(output_dir).name)
        if Path(pre_refine_dir).exists():
            shutil.rmtree(pre_refine_dir)
        Path(pre_refine_dir).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output_dir, pre_refine_dir)

        verify_and_refine(output_dir, logs_dir, model, api_key=api_key)

        # If verify_and_refine broke it, restore the post-execute snapshot
        refine_ok = (Path(output_dir) / "index.html").exists() and _check_js_compilation(output_dir)
        if not refine_ok:
            print("  [safety] verify_and_refine broke output, restoring post-execute version")
            _restore_backup(pre_refine_dir, output_dir)
        else:
            shutil.rmtree(pre_refine_dir)

        _cleanup_backup(backup_dir)
        return True

    # Execute itself failed — restore previous version or clean up
    if had_previous:
        _restore_backup(backup_dir, output_dir)
        return True
    _clean_output(output_dir)
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute a moment task")
    parser.add_argument("task_path", help="Path to the task .md file")
    parser.add_argument("output_dir", help="Directory to write HTML output")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("--api-key", default=None, help="API key (default: from config or $ANTHROPIC_API_KEY)")
    args = parser.parse_args()
    model = args.model or resolve_moments_model()
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or resolve_moments_api_key()

    success = run(args.task_path, args.output_dir, args.logs_dir, model=model, api_key=api_key)
    print("Success" if success else "Failed")
