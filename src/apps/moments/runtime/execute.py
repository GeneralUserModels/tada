"""Execute a moment task: run the agent, build an interface for the result."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments.runtime.verify_refine import verify_and_refine

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

OUTPUT_FILES = ["index.html", "styles.css", "app.js", "data.js", "base.css", "components.js", "meta.json"]
EXECUTE_WARNING_ROUND = 100
EXECUTE_MAX_ROUNDS = 150

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
INSTRUCTION_TEMPLATE = (_PROMPTS / "execute.txt").read_text()
UPDATE_INSTRUCTION_TEMPLATE = (_PROMPTS / "execute_update.txt").read_text()
SHARED_SOURCES = (_PROMPTS / "shared" / "sources.txt").read_text()
SHARED_INTERFACE = (_PROMPTS / "shared" / "interface.txt").read_text()
SHARED_EXECUTOR_CAPABILITIES = (_PROMPTS / "shared" / "executor_capabilities.txt").read_text()
EXECUTE_RULES = (_PROMPTS / "rules" / "execute.txt").read_text()
EXECUTE_UPDATE_RULES = (_PROMPTS / "rules" / "execute_update.txt").read_text()



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
    cadence_override: str | None = None,
    schedule_override: str | None = None,
    api_key: str | None = None,
    last_run_at: float | None = None,
    on_round=None,
    subagent_model: str | None = None,
    subagent_api_key: str | None = None,
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

    effective_cadence = cadence_override or fm.get("cadence", "")
    effective_schedule = schedule_override or fm.get("schedule", "")

    # Read user feedback files and state (thumbs, dismissed, etc.)
    feedback_section = ""
    slug = Path(output_dir).name
    tada_dir = Path(output_dir).parent.parent
    state_path = tada_dir / "results" / "_moment_state.json"
    if state_path.exists():
        all_state = json.loads(state_path.read_text())
        slug_state = all_state.get(slug, {})
        thumbs = slug_state.get("thumbs")
        if thumbs:
            feedback_section += f"\n\n## User Rating\n\nThe user gave this moment a **thumbs {thumbs}**."

    feedback_files = sorted(Path(output_dir).glob("feedback_*.md"))
    if feedback_files:
        parts = []
        for f in feedback_files:
            parts.append(f"### {f.stem}\n\n{f.read_text()}")
        feedback_section += (
            "\n\n## User Feedback\n\n"
            "The user has provided feedback on previous versions of this moment. Incorporate this feedback "
            "into your output — address their concerns, adjust the content or presentation accordingly.\n\n"
            + "\n\n".join(parts)
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing_index = Path(output_dir) / "index.html"
    if existing_index.exists():
        last_run_str = datetime.fromtimestamp(last_run_at).strftime("%Y-%m-%d %H:%M") if last_run_at else "unknown"
        instruction = f"Current date and time: **{now}**\n\n" + UPDATE_INSTRUCTION_TEMPLATE.format(
            task_content=task_content,
            output_dir=output_dir,
            logs_dir=logs_dir,
            cadence=effective_cadence,
            schedule=effective_schedule,
            last_run_at=last_run_str,
            shared_sources=SHARED_SOURCES.format(logs_dir=logs_dir),
            shared_interface=SHARED_INTERFACE,
            shared_executor_capabilities=SHARED_EXECUTOR_CAPABILITIES,
            execute_update_rules=EXECUTE_UPDATE_RULES.format(output_dir=output_dir, logs_dir=logs_dir),
        ) + feedback_section
    else:
        instruction = f"Current date and time: **{now}**\n\n" + INSTRUCTION_TEMPLATE.format(
            task_content=task_content,
            output_dir=output_dir,
            logs_dir=logs_dir,
            cadence=effective_cadence,
            schedule=effective_schedule,
            templates_dir=str(TEMPLATES_DIR),
            shared_sources=SHARED_SOURCES.format(logs_dir=logs_dir),
            shared_interface=SHARED_INTERFACE,
            shared_executor_capabilities=SHARED_EXECUTOR_CAPABILITIES,
            execute_rules=EXECUTE_RULES.format(output_dir=output_dir, logs_dir=logs_dir),
        )

    agent, _ = build_agent(
        model, logs_dir, extra_write_dirs=[output_dir], api_key=api_key,
        subagent_model=subagent_model, subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = EXECUTE_MAX_ROUNDS
    agent.warning_round = EXECUTE_WARNING_ROUND
    agent.on_round = on_round
    agent.run([{"role": "user", "content": instruction}])

    # Write meta.json as fallback if agent didn't
    meta_path = Path(output_dir) / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "title": fm.get("title", Path(task_path).stem),
            "description": fm.get("description", ""),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "cadence": effective_cadence,
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

        # Mark any feedback as incorporated
        if feedback_files:
            from apps.moments.core.state import load_state, save_state
            tada_dir = Path(output_dir).parent.parent
            all_state = load_state(tada_dir)
            slug = Path(output_dir).name
            entry = {**all_state.get(slug, {})}
            entry["last_feedback_incorporated_at"] = datetime.now(timezone.utc).isoformat()
            all_state[slug] = entry
            save_state(tada_dir, all_state)

        _cleanup_backup(backup_dir)
        return True

    # Execute itself failed — restore previous version or clean up
    if had_previous:
        _restore_backup(backup_dir, output_dir)
        return True
    _clean_output(output_dir)
    return False
