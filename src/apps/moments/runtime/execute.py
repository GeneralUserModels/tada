"""Execute a moment task: run the agent, build an interface for the result."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

load_dotenv()

from agent.builder import build_agent
from apps.moments.runtime.verify_refine import verify_and_refine

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

OUTPUT_FILES = [
    "index.html", "styles.css", "app.js", "data.js", "base.css", "components.js",
    "research", "templates", "meta.json",
]
RESEARCH_WARNING_ROUND = 60
RESEARCH_MAX_ROUNDS = 90
BUILD_WARNING_ROUND = 80
BUILD_MAX_ROUNDS = 110
SHARED_ASSETS = {
    "base.css": TEMPLATES_DIR / "shared" / "base.css",
    "components.js": TEMPLATES_DIR / "shared" / "components.js",
}

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
RESEARCH_INSTRUCTION_TEMPLATE = (_PROMPTS / "execute_research.txt").read_text()
BUILD_INSTRUCTION_TEMPLATE = (_PROMPTS / "execute_build.txt").read_text()
SHARED_SOURCES = (_PROMPTS / "shared" / "sources.txt").read_text()
SHARED_INTERFACE = (_PROMPTS / "shared" / "interface.txt").read_text()
SHARED_EXECUTOR_CAPABILITIES = (_PROMPTS / "shared" / "executor_capabilities.txt").read_text()



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


class _HtmlAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "script" and attr.get("src"):
            self.assets.append(attr["src"] or "")
        elif tag == "link" and attr.get("rel") == "stylesheet" and attr.get("href"):
            self.assets.append(attr["href"] or "")


def _ensure_shared_assets(output_dir: str) -> None:
    """Place shared runtime files next to generated moment files."""
    out = Path(output_dir)
    for name, src in SHARED_ASSETS.items():
        dst = out / name
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)


def _normalize_shared_asset_refs(output_dir: str) -> None:
    """Keep generated HTML using sibling shared assets in the result directory."""
    index_path = Path(output_dir) / "index.html"
    if not index_path.exists():
        return
    html = index_path.read_text()
    normalized = (
        html
        .replace('href="../shared/base.css"', 'href="base.css"')
        .replace("href='../shared/base.css'", "href='base.css'")
        .replace('src="../shared/components.js"', 'src="components.js"')
        .replace("src='../shared/components.js'", "src='components.js'")
    )
    if normalized != html:
        index_path.write_text(normalized)


def _prepare_shared_runtime(output_dir: str) -> None:
    _ensure_shared_assets(output_dir)
    _normalize_shared_asset_refs(output_dir)


def _clear_generated_output(output_dir: str) -> None:
    """Remove prior generated artifacts while preserving feedback files."""
    out = Path(output_dir)
    for name in OUTPUT_FILES:
        path = out / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _copy_template_kit(output_dir: str) -> Path:
    """Copy all template examples into the result directory for build-time reference."""
    kit_dir = Path(output_dir) / "templates"
    if kit_dir.exists():
        shutil.rmtree(kit_dir)
    kit_dir.mkdir(parents=True)
    for template_dir in sorted(TEMPLATES_DIR.iterdir()):
        if template_dir.is_dir():
            shutil.copytree(template_dir, kit_dir / template_dir.name)
    return kit_dir


def _check_html_asset_refs(output_dir: str) -> bool:
    """Verify local scripts and stylesheets referenced by index.html exist."""
    out = Path(output_dir)
    index_path = out / "index.html"
    if not index_path.exists():
        return False
    parser = _HtmlAssetParser()
    parser.feed(index_path.read_text())
    ok = True
    for ref in parser.assets:
        parsed = urlparse(ref)
        if parsed.scheme or ref.startswith(("//", "#", "data:")):
            continue
        asset_path = (out / unquote(parsed.path)).resolve()
        if not asset_path.exists():
            print(f"  [assets] MISSING: {ref}")
            ok = False
    return ok


def _check_output(output_dir: str) -> bool:
    if not (Path(output_dir) / "index.html").exists():
        return False
    _prepare_shared_runtime(output_dir)
    return _check_html_asset_refs(output_dir) and _check_js_compilation(output_dir)


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


def _research_ready(research_dir: str) -> bool:
    path = Path(research_dir)
    if not path.is_dir():
        return False
    md_files = [p for p in path.glob("*.md") if p.is_file()]
    return len(md_files) >= 2 and all(p.read_text().strip() for p in md_files)


def _build_agent_for_stage(
    model: str,
    logs_dir: str,
    output_dir: str,
    api_key: str | None,
    subagent_model: str | None,
    subagent_api_key: str | None,
    *,
    max_rounds: int,
    warning_round: int,
    on_round=None,
):
    agent, _ = build_agent(
        model, logs_dir, extra_write_dirs=[output_dir], api_key=api_key,
        subagent_model=subagent_model, subagent_api_key=subagent_api_key,
    )
    agent.max_rounds = max_rounds
    agent.warning_round = warning_round
    agent.on_round = on_round
    return agent


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
    _clear_generated_output(output_dir)

    # Make the shared runtime available before the agent writes app code, so
    # generated interfaces can inspect and rely on these files directly.
    _prepare_shared_runtime(output_dir)

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
    research_dir = str(Path(output_dir) / "research")
    research_instruction = f"Current date and time: **{now}**\n\n" + RESEARCH_INSTRUCTION_TEMPLATE.format(
        task_content=task_content,
        cadence=effective_cadence,
        schedule=effective_schedule,
        research_dir=research_dir,
        shared_sources=SHARED_SOURCES.format(logs_dir=logs_dir),
        shared_executor_capabilities=SHARED_EXECUTOR_CAPABILITIES,
    ) + feedback_section

    research_agent = _build_agent_for_stage(
        model, logs_dir, output_dir, api_key, subagent_model, subagent_api_key,
        max_rounds=RESEARCH_MAX_ROUNDS, warning_round=RESEARCH_WARNING_ROUND, on_round=on_round,
    )
    research_agent.run([{"role": "user", "content": research_instruction}])

    if not _research_ready(research_dir):
        research_repair_instruction = research_instruction + (
            "\n\n## Required Repair\n\n"
            f"The required research folder is not ready at `{research_dir}`. Your previous attempt did not "
            "write the required markdown files. Do not plan, do not only create directories, and do not build "
            "the website. Use the `write_file` tool now to write at least two substantive non-empty markdown "
            f"files inside `{research_dir}`, verify they exist, and then stop."
        )
        research_agent.run([{"role": "user", "content": research_repair_instruction}])

    if not _research_ready(research_dir):
        print("  [research] FAILED: research markdown files were not written")
        if had_previous:
            _restore_backup(backup_dir, output_dir)
            return True
        _clean_output(output_dir)
        return False

    template_kit_dir = _copy_template_kit(output_dir)
    _prepare_shared_runtime(output_dir)

    build_instruction = f"Current date and time: **{now}**\n\n" + BUILD_INSTRUCTION_TEMPLATE.format(
        task_content=task_content,
        output_dir=output_dir,
        cadence=effective_cadence,
        schedule=effective_schedule,
        research_dir=research_dir,
        template_kit_dir=str(template_kit_dir),
        shared_interface=SHARED_INTERFACE,
    ) + feedback_section

    build_agent = _build_agent_for_stage(
        model, logs_dir, output_dir, api_key, subagent_model, subagent_api_key,
        max_rounds=BUILD_MAX_ROUNDS, warning_round=BUILD_WARNING_ROUND, on_round=on_round,
    )
    build_agent.run([{"role": "user", "content": build_instruction}])

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

    # Check if execute produced a valid output before running verify_and_refine.
    # Syntax checks alone are insufficient: app.js can be valid JS while the
    # HTML points at missing shared runtime files, causing runtime crashes.
    execute_ok = _check_output(output_dir)

    if execute_ok:
        # Snapshot post-execute state so we can recover if verify_and_refine breaks it
        pre_refine_dir = str(Path(output_dir).parent / "_pre_refine" / Path(output_dir).name)
        if Path(pre_refine_dir).exists():
            shutil.rmtree(pre_refine_dir)
        Path(pre_refine_dir).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output_dir, pre_refine_dir)

        verify_and_refine(output_dir, logs_dir, model, api_key=api_key)

        # If verify_and_refine broke it, restore the post-execute snapshot
        refine_ok = _check_output(output_dir)
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
