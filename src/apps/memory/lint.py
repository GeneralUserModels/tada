"""Lint and maintain the personal knowledge wiki."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint


LINT_TEMPLATE = """\
You are a wiki quality reviewer. Your job is to audit and maintain the personal knowledge wiki at \
{memory_dir}/. You do NOT read raw activity logs — you only work on the wiki itself.

You have full tool access:
- **bash**: Scan directory tree, run Python to analyze frontmatter across all pages, detect duplicates \
programmatically, compute age/staleness metrics, build a wiki-link graph. Don't manually read every \
page — write code to process them in bulk.
- **read_file** / **edit_file**: Read and fix wiki pages.
- **web_search** / **browser_navigate**: Verify facts — if a wiki page claims the user works at X or \
a person holds role Y, spot-check with a web search and update if stale.
- **subagent**: Parallelize checks across different wiki directories.
- **PlanWrite** / **PlanUpdate**: Plan your approach and track progress.

## Wiki conventions

Pages are markdown with YAML frontmatter:
```
---
title: <Page Title>
confidence: <0.0-1.0>
last_updated: <YYYY-MM-DD>
---
```

Pages use [[wiki-links]] to cross-reference. A link [[Page Name]] resolves by slugifying to \
page-name.md. Links can include paths: [[hobbies/Rock Climbing]] → hobbies/rock-climbing.md.

## Workflow

Start by using bash to run a Python script that:
1. Recursively finds all .md files in {memory_dir}/
2. Parses their YAML frontmatter (title, confidence, last_updated)
3. Extracts all [[wiki-links]] from each page
4. Builds a report: total pages, broken links, pages missing frontmatter, confidence distribution, \
pages not updated in 14+ days, pages with confidence < 0.2 and last_updated > 30 days

Then use that report to guide your manual review and fixes.

## Checks to perform

### 1. Index consistency
Read {memory_dir}/index.md. Compare against the actual files on disk. Every page on disk must be in \
the index; every index entry must correspond to a real file. Fix discrepancies.

### 2. Broken wiki-links
For every [[wiki-link]] in every page, verify the target file exists. If broken, either fix the link \
(if the target was renamed) or remove the link (if the target no longer exists).

### 3. Stale page archival
Pages with confidence < 0.2 AND last_updated older than 30 days should be archived. Move them to \
{memory_dir}/_archive/, remove from index.md, and log the archival.

### 4. Confidence decay
Pages not updated in 14+ days should have confidence reduced by 0.1 (floor at 0.1). Update the \
last_updated field when adjusting confidence.

### 5. Duplicate content
Identify pages with substantially overlapping content. Merge into one page, redirect wiki-links, \
update index.md.

### 6. Structural coherence
If a category folder has grown to 10+ pages, consider whether subcategories help. If a folder has \
only 1 page, consider merging it into the parent. Only restructure when it clearly improves \
navigability — don't force reorganization.

### 7. Cross-referencing
Identify pages that discuss related topics but don't link to each other. Add [[wiki-links]] where \
natural connections exist.

### 8. Schema compliance
Every page must have the required frontmatter (title, confidence, last_updated). Fix any pages \
missing these fields.

### 9. Fact verification
For high-confidence (>0.7) pages about people, companies, or projects, spot-check key claims with \
web_search. Update if information is outdated.

## After lint

Append a summary to {memory_dir}/log.md:
```
## YYYY-MM-DD (lint)
- Fixed N broken links
- Archived M stale pages
- Applied confidence decay to Y pages
- Merged X duplicate pages
- Added cross-references between ...
- Verified facts on ...
```

## Rules

- Do NOT create new wiki pages from scratch — that is the ingest agent's job.
- Do NOT read raw activity logs.
- Do NOT delete pages outright — archive them to _archive/ instead.
- Preserve all content when merging — combine rather than discard.
"""


def run(logs_dir: str, model: str, api_key: str | None = None) -> str:
    logs_path = Path(logs_dir).resolve()
    memory_dir = logs_path / "memory"

    if not memory_dir.exists():
        return "Wiki directory does not exist yet. Run ingest first."

    checkpoint_path = memory_dir / ".last_lint"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + LINT_TEMPLATE.format(
        memory_dir=str(memory_dir),
    )

    agent, _ = build_agent(model, str(logs_path), api_key=api_key)
    agent.max_rounds = 100
    result = agent.run([{"role": "user", "content": instruction}])

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    import logging

    from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model
    from server.cost_tracker import init_cost_tracking

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Lint and maintain the personal knowledge wiki")
    parser.add_argument("logs_dir", help="Path to the logs directory")
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    tracker = init_cost_tracking()

    model = args.model or resolve_moments_model()
    api_key = args.api_key or resolve_moments_api_key()

    result = run(args.logs_dir, model=model, api_key=api_key)
    print(result)

    snapshot, elapsed = tracker.snapshot()
    total_cost = sum(s["cost"] for s in snapshot.values())
    total_tokens = sum(s["input_tokens"] + s["output_tokens"] for s in snapshot.values())
    logging.getLogger(__name__).info(
        "[cost] lint finished — $%.4f total, %d tokens, %.0fs", total_cost, total_tokens, elapsed
    )
