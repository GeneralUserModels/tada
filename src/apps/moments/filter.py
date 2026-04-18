"""Filter task definitions: read all candidates, rank them, copy the best N to logs-tada/."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments._incremental import read_checkpoint, write_checkpoint
from apps.moments.cli_config import resolve_moments_api_key, resolve_moments_model

INSTRUCTION_TEMPLATE = """\
You are a strict filter. Your job is to incrementally select only the BEST task candidates and copy \
them to {tada_dir}/. Be very picky — most candidates should be rejected. Only pass through tasks that \
are clearly high-value, specific, and grounded in real observed behavior.

## Source directories

- **Moments** (recurring tasks): {tasks_dir}/
- **One-offs** (situational tasks): {oneoffs_dir}/

## Output directory

- **Selected tasks**: {tada_dir}/

## Agent capabilities (for judging whether a task is completable)

The agent that will execute these tasks is powerful. It can:
- Search the web, crawl pages, and fetch live data
- Browse authenticated websites (GitHub, Gmail, Twitter/X, YouTube, Slack, Google Docs, etc.) using the user's Chrome cookies
- Do deep research and analysis — read papers, compare approaches, synthesize across dozens of sources
- Read files on the user's machine for context
- Run shell commands, scripts, git operations, Python/Node code
- Pre-draft emails, Slack messages, documents, and code for the user to review
- Generate reports, build slide decks, create static HTML interfaces to present results
- Spawn subagents to parallelize work across different data sources
- Read local logs: notifications, calendar, email, filesystem changes, screen sessions

The agent CANNOT: call LLMs at runtime in its output, modify arbitrary files on the user's machine, \
or build interactive interfaces that require a backend. It produces static artifacts (HTML, markdown, \
drafts) that the user reviews.

Every task is run as a one-shot execution (not a daemon). "Daily digest" means "generate one now."

**When ranking, prioritize tasks that amplify the user's abilities:**
- **Information foraging and synthesis** — deep research, comparing tools/approaches, reading \
papers/docs, compiling structured knowledge. This is where the agent provides the most value.
- **Complex multi-step workflows** — ambitious tasks that chain many operations together.
- **"Extra-mile" work** — things the user would benefit from but never gets around to doing.
Deprioritize simple, shallow tasks that a human could do in a few minutes.

## User signals on past tadas

Before evaluating candidates, read `{tada_dir}/results/_moment_state.json` to see how the user has \
reacted to existing tadas — thumbs up/down, dismissed, pinned, view counts. Also check for \
`feedback_*.md` files in each result directory (`{tada_dir}/results/*/feedback_*.md`) — these contain \
conversational feedback about what the user liked or disliked. Use these signals to calibrate your \
filtering: favor candidates similar to thumbs-up/pinned tadas, reject candidates similar to \
dismissed/thumbs-down ones.

## Steps

1. Run `ls {tada_dir}/` to see which tasks have already been selected.
2. Read `{tada_dir}/results/_moment_state.json` and scan for feedback files to understand user preferences.
3. Read ALL candidate `.md` files from {tasks_dir}/ and {oneoffs_dir}/. Use subagents to read \
them in parallel — each subagent should read a batch of files and return a summary of each \
(title, source dir, what it does, and a 1-10 quality score based on: grounded in real behavior, \
genuinely useful, completable by the agent).
4. For each candidate, decide whether to copy it. Default to REJECTING — only copy tasks that pass \
ALL of these bars:
  - Clearly grounded in specific observed user behavior (not generic productivity advice)
  - Produces a concrete, useful artifact (summary, draft, report, analysis)
  - Completable by the agent with its available tools in a single run
  - Not a duplicate or near-duplicate of a task already in {tada_dir}/
  - Not vague, fluffy, or overly broad
  - Not reactive/trigger-based ("when X happens, do Y")
  - Does not require macOS accessibility/window-management APIs
  Prefer diversity — avoid copying tasks that overlap with existing ones in {tada_dir}/.
5. Copy the good candidates to {tada_dir}/<filename>.md using write_file. Aim to keep up to {n} \
total tasks in {tada_dir}/. Do NOT delete any files — not from source dirs and not from {tada_dir}/.
6. Print which tasks you copied and why, and which you skipped and why.
7. Run `ls {tada_dir}/` to verify.
"""

INCREMENTAL_SECTION = """\

## Incremental Filter

This is a RE-RUN. The last filter was on **{last_filter_date}**. Prioritize evaluating new \
candidates, but review all candidates thoroughly.

### New candidates since last filter (prioritize these):
{new_candidates_list}

### Previously evaluated candidates:
{old_candidates_list}

"""


def _classify_candidates(dirs: list[str], since: datetime | None) -> tuple[list[str], list[str]]:
    """Return (new, old) candidate .md file paths based on mtime vs checkpoint."""
    all_files: list[tuple[float, str]] = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.glob("*.md"):
            all_files.append((f.stat().st_mtime, str(f)))
    all_files.sort(key=lambda x: x[0])
    if since is None:
        return [path for _, path in all_files], []
    cutoff = since.timestamp()
    new = [path for mtime, path in all_files if mtime > cutoff]
    old = [path for mtime, path in all_files if mtime <= cutoff]
    return new, old


def run(logs_dir: str, n: int = 10, model: str | None = None, api_key: str | None = None) -> str:
    logs_path = Path(logs_dir).resolve()
    tasks_dir = str(logs_path / "tasks")
    oneoffs_dir = str(logs_path / "oneoffs")
    tada_dir = str(logs_path.parent / "logs-tada")
    checkpoint_path = logs_path / "tasks" / ".last_filter"
    Path(tada_dir).mkdir(parents=True, exist_ok=True)
    model = model or resolve_moments_model()
    agent, _ = build_agent(model, logs_dir, api_key=api_key)
    agent.max_rounds = 50

    last_filter = read_checkpoint(checkpoint_path)
    new_candidates, old_candidates = _classify_candidates([tasks_dir, oneoffs_dir], last_filter)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(
        tasks_dir=tasks_dir, oneoffs_dir=oneoffs_dir, tada_dir=tada_dir, n=n
    )

    if last_filter is not None and new_candidates:
        new_list = "\n".join(f"- {p}" for p in new_candidates)
        old_list = "\n".join(f"- {p}" for p in old_candidates) if old_candidates else "- (none)"
        instruction += INCREMENTAL_SECTION.format(
            last_filter_date=last_filter.strftime("%Y-%m-%d %H:%M"),
            new_candidates_list=new_list,
            old_candidates_list=old_list,
        )
    elif last_filter is not None and not new_candidates:
        instruction += (
            f"\n\n## Note\n\nThe last filter was on "
            f"**{last_filter.strftime('%Y-%m-%d %H:%M')}** and there are no new candidates "
            f"since then. Review existing candidates and {tada_dir}/ for any missed tasks."
        )

    messages = [{"role": "user", "content": instruction}]
    result = agent.run(messages)

    write_checkpoint(checkpoint_path)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter tasks: rank all candidates and copy the best N to logs-tada/")
    parser.add_argument("logs_dir", help="Path to the logs directory (e.g., logs/)")
    parser.add_argument("-n", "--num-tasks", type=int, default=10, help="Number of top tasks to keep (default: 10)")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    model = args.model or resolve_moments_model()

    result = run(args.logs_dir, n=args.num_tasks, model=model, api_key=resolve_moments_api_key())
    print(result)
