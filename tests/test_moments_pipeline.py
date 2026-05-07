from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apps.moments.steps import discover, promote
from apps.common import structured_completion as structured_completion_module
from apps.common.structured_ops import StructuredOpsError, extract_json_object
from apps.moments.core.candidates import (
    CandidateError,
    parse_discovery_result,
    parse_promotion_result,
    render_accepted_markdown,
    validate_candidate,
    write_candidates_jsonl,
)
from apps.moments.core.paths import migrate_moments_to_cadence
from apps.moments.runtime import execute
from apps.moments.runtime.scheduler import scheduled_service_due, should_run
from apps.moments.schemas.structured import DraftActionPayload


def _candidate(**overrides):
    base = {
        "id": "paper-digest",
        "slug": "paper-digest",
        "topic": "research",
        "title": "Paper Digest",
        "description": "Track relevant papers.",
        "cadence": "scheduled",
        "schedule": "daily at 8am",
        "trigger": "",
        "confidence": 0.8,
        "usefulness": 8,
        "specific_instructions": "Find new papers and summarize why they matter.",
        "desired_artifact": "A ranked feed of papers.",
        "evidence": ["memory/index.md mentions research"],
        "source_paths": ["memory/index.md"],
        "why_now": "The user is actively researching.",
        "user_value": "Saves triage time.",
    }
    base.update(overrides)
    return base


def _idea(**overrides):
    base = {
        "title": "Paper Digest",
        "topic_hint": "research",
        "artifact": "A ranked feed of papers.",
        "why_useful": "Saves triage time.",
        "evidence": ["memory/index.md mentions research"],
        "source_paths": ["memory/index.md"],
        "cadence_hint": "scheduled",
        "relation_to_existing": "new",
    }
    base.update(overrides)
    return base


class _FakeStructuredCompletion:
    def __init__(self, *results: str | Exception):
        self.results = list(results)
        self.instructions: list[str] = []

    def __call__(self, *, instruction, response_model, **kwargs):
        self.instructions.append(instruction)
        if not self.results:
            raise AssertionError("No fake structured completion result queued")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        try:
            payload = extract_json_object(result)
        except StructuredOpsError:
            try:
                payload = json.loads(result)
            except json.JSONDecodeError as exc:
                raise StructuredOpsError(f"invalid JSON: {exc}") from exc
        try:
            parsed = response_model.model_validate(payload)
        except ValidationError as exc:
            raise StructuredOpsError(f"structured output validation failed: {exc}") from exc
        return result, parsed


class _FakeToolAgent:
    def __init__(self, *results: str):
        self.results = list(results) or ["```json\n" + json.dumps({"ideas": [_idea()], "notes": ""}) + "\n```"]
        self.max_rounds = None
        self.on_round = None
        self.messages: list[list[dict]] = []

    def run(self, messages, **kwargs):
        self.messages.append(messages)
        if not self.results:
            raise AssertionError("No fake tool agent result queued")
        return self.results.pop(0)


class _FakeExecuteAgent:
    def __init__(self, output_dir: Path, stage: str, test_case: unittest.TestCase):
        self.output_dir = output_dir
        self.stage = stage
        self.test_case = test_case
        self.max_rounds = None
        self.warning_round = None
        self.on_round = None
        self.messages: list[list[dict]] = []

    def run(self, messages, **kwargs):
        self.messages.append(messages)
        prompt = messages[0]["content"]
        if self.stage == "research":
            self.test_case.assertIn("/research", prompt)
            research_dir = self.output_dir / "research"
            research_dir.mkdir(parents=True)
            (research_dir / "evidence.md").write_text("# Evidence\n\nA cited source.\n")
            (research_dir / "synthesis.md").write_text("# Synthesis\n\nUseful researched findings.\n")
            return "research complete"

        research_dir = self.output_dir / "research"
        self.test_case.assertGreaterEqual(len(list(research_dir.glob("*.md"))), 2)
        self.test_case.assertFalse((self.output_dir / "index.html").exists())
        self.test_case.assertFalse((self.output_dir / "styles.css").exists())
        self.test_case.assertFalse((self.output_dir / "app.js").exists())
        self.test_case.assertTrue((self.output_dir / "base.css").exists())
        self.test_case.assertTrue((self.output_dir / "components.js").exists())
        template_kit_dir = self.output_dir / "templates"
        for template_name in ("blank", "dashboard", "feed", "report", "table", "shared"):
            self.test_case.assertTrue((template_kit_dir / template_name).is_dir(), template_name)
            self.test_case.assertTrue((template_kit_dir / template_name / "README.md").exists(), template_name)
        self.test_case.assertTrue((template_kit_dir / "feed" / "app.js").exists())
        self.test_case.assertTrue((template_kit_dir / "dashboard" / "index.html").exists())
        self.test_case.assertIn(str(research_dir), prompt)
        self.test_case.assertIn(str(template_kit_dir), prompt)
        self.test_case.assertNotIn("{template_kit_dir}", prompt)
        self.test_case.assertIn("template kit has been copied", prompt)
        self.test_case.assertIn("multiple views, tabs, filters", prompt)
        self.test_case.assertIn("copying and pasting directly", prompt)
        self.test_case.assertIn("Every substantive research file needs a visible home", prompt)
        self.test_case.assertIn("Do not invent a separate visual system", prompt)
        self.test_case.assertIn("Do not introduce blue/purple fallback accents", prompt)
        shutil.copyfile(template_kit_dir / "feed" / "index.html", self.output_dir / "index.html")
        shutil.copyfile(template_kit_dir / "feed" / "styles.css", self.output_dir / "styles.css")
        shutil.copyfile(template_kit_dir / "feed" / "app.js", self.output_dir / "app.js")
        (self.output_dir / "meta.json").write_text(json.dumps({
            "title": "Strategy Brief",
            "description": "Built from template kit.",
            "completed_at": "2026-05-06T00:00:00Z",
            "cadence": "once",
            "schedule": "",
        }))
        return "build complete"


class _FakeMissingResearchAgent:
    def __init__(self):
        self.max_rounds = None
        self.warning_round = None
        self.on_round = None
        self.messages: list[list[dict]] = []

    def run(self, messages, **kwargs):
        self.messages.append(messages)
        return "no file written"


def _filtered_row(timestamp: datetime, source_name: str, text: str, **extra):
    row = {
        "timestamp": timestamp.timestamp(),
        "source_name": source_name,
        "text": text,
        "source": {},
    }
    row.update(extra)
    return json.dumps(row)


class MomentsPipelineTests(unittest.TestCase):
    def test_scheduled_services_wait_on_first_launch_but_catch_up_after_schedule(self):
        with tempfile.TemporaryDirectory() as d:
            last_run = Path(d) / ".discovery_last_run"
            self.assertFalse(scheduled_service_due("daily at 2am", last_run))
            self.assertTrue(last_run.exists())
            last_run.write_text(datetime(2000, 1, 1).isoformat())
            self.assertTrue(scheduled_service_due("daily at 2am", last_run))

    def test_candidate_validation_for_cadences(self):
        self.assertEqual(validate_candidate(_candidate(cadence="once", schedule="daily at 8am")).schedule, "")
        self.assertEqual(validate_candidate(_candidate(cadence="trigger", schedule="", trigger="a deadline appears")).trigger, "a deadline appears")
        with self.assertRaises(CandidateError):
            validate_candidate(_candidate(cadence="scheduled", schedule=""))
        with self.assertRaises(CandidateError):
            validate_candidate(_candidate(cadence="trigger", trigger=""))

    def test_markdown_render_uses_cadence_frontmatter(self):
        candidate = validate_candidate(_candidate(cadence="scheduled", schedule="Monday at 9am"))
        markdown = render_accepted_markdown(candidate)
        self.assertIn("cadence: scheduled", markdown)
        self.assertIn("schedule: Monday at 9am", markdown)
        self.assertNotIn("frequency:", markdown)

    def test_parse_promotion_selects_candidates(self):
        candidates = parse_discovery_result("```json\n" + json.dumps({"candidates": [_candidate()]}) + "\n```")
        promoted, rejected = parse_promotion_result(
            '```json\n{"ranked":[{"id":"paper-digest","score":9,"reason":"useful"}],"rejected":[]}\n```',
            candidates,
        )
        self.assertEqual([c.slug for c in promoted], ["paper-digest"])
        self.assertEqual(rejected, [])

    def test_migration_rewrites_frequency_to_cadence_and_state(self):
        with tempfile.TemporaryDirectory() as d:
            tada = Path(d) / "logs-tada"
            topic = tada / "research"
            topic.mkdir(parents=True)
            (topic / "daily.md").write_text(
                "---\n"
                "title: Daily\n"
                "description: Desc\n"
                "frequency: daily\n"
                "schedule: at 8am\n"
                "confidence: 0.8\n"
                "usefulness: 8\n"
                "---\n\nBody\n"
            )
            state = tada / "results" / "_moment_state.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({"daily": {"frequency_override": "weekly"}}))

            changed = migrate_moments_to_cadence(tada)

            self.assertGreaterEqual(changed, 2)
            text = (topic / "daily.md").read_text()
            self.assertIn("cadence: scheduled", text)
            self.assertNotIn("frequency:", text)
            self.assertEqual(json.loads(state.read_text())["daily"]["cadence_override"], "scheduled")

    def test_scheduler_respects_cadence(self):
        self.assertTrue(should_run("once", "once", "", {}))
        self.assertFalse(should_run("trigger", "trigger", "", {}))
        self.assertTrue(should_run("daily", "scheduled", "daily at 12:01am", {}))

    def test_shared_components_only_export_pn_global(self):
        components_js = (execute.TEMPLATES_DIR / "shared" / "components.js").read_text()

        self.assertIn("(function() {", components_js)
        self.assertIn("window.PN = {", components_js)
        self.assertTrue(components_js.rstrip().endswith("})();"))

    def test_template_apps_define_local_react_helpers(self):
        for app_js in sorted(execute.TEMPLATES_DIR.glob("*/app.js")):
            text = app_js.read_text()
            self.assertIn("const h = React.createElement", text, f"{app_js} should define local h helper")

    def test_shared_component_classes_have_base_styles(self):
        components_js = (execute.TEMPLATES_DIR / "shared" / "components.js").read_text()
        base_css = (execute.TEMPLATES_DIR / "shared" / "base.css").read_text()

        class_tokens = set()
        for match in re.finditer(r'className:\s*"([^"]+)"', components_js):
            class_tokens.update(token for token in match.group(1).split() if token)

        missing = sorted(token for token in class_tokens if f".{token}" not in base_css)
        self.assertFalse(missing, f"Shared component classes missing base.css styles: {missing}")

    def test_shared_interface_does_not_tell_builder_to_write_runtime_assets(self):
        interface_text = (execute._PROMPTS / "shared" / "interface.txt").read_text()
        generated_files = interface_text.split("Use the provided templates", 1)[0]

        self.assertIn("Create or update these generated files:", generated_files)
        self.assertIn("`index.html`", generated_files)
        self.assertIn("`styles.css`", generated_files)
        self.assertIn("`app.js`", generated_files)
        self.assertIn("`meta.json`", generated_files)
        self.assertNotIn("`base.css`", generated_files)
        self.assertNotIn("`components.js`", generated_files)

    def test_execute_splits_research_and_template_bound_build(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            logs.mkdir()
            tada = root / "logs-tada"
            task_dir = tada / "research"
            task_dir.mkdir(parents=True)
            task_path = task_dir / "strategy-brief.md"
            task_path.write_text(
                "---\n"
                "title: Strategy Brief\n"
                "description: Prepare a concise interview briefing.\n"
                "cadence: once\n"
                "confidence: 0.80\n"
                "usefulness: 8\n"
                "---\n\n"
                "## Specific Instructions for Agent\n\n"
                "Create a brief report from the evidence.\n\n"
                "## Desired Artifact\n\n"
                "Structured report.\n\n"
                "## Evidence\n\n"
                "- memory/index.md mentions an interview thread\n"
            )
            output_dir = tada / "results" / "strategy-brief"
            output_dir.mkdir(parents=True)
            research_agent = _FakeExecuteAgent(output_dir, "research", self)
            build_agent = _FakeExecuteAgent(output_dir, "build", self)

            with patch.object(execute, "build_agent", side_effect=[(research_agent, None), (build_agent, None)]), \
                 patch.object(execute, "verify_and_refine", return_value=True):
                success = execute.run(str(task_path), str(output_dir), str(logs), model="fake")

            self.assertTrue(success)
            self.assertGreaterEqual(len(list((output_dir / "research").glob("*.md"))), 2)
            self.assertEqual(len(research_agent.messages), 1)
            self.assertEqual(len(build_agent.messages), 1)

    def test_execute_fails_before_build_when_research_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            logs.mkdir()
            tada = root / "logs-tada"
            task_dir = tada / "research"
            task_dir.mkdir(parents=True)
            task_path = task_dir / "strategy-brief.md"
            task_path.write_text(
                "---\n"
                "title: Strategy Brief\n"
                "description: Prepare a concise interview briefing.\n"
                "cadence: once\n"
                "confidence: 0.80\n"
                "usefulness: 8\n"
                "---\n\n"
                "## Specific Instructions for Agent\n\n"
                "Create a brief report from the evidence.\n"
            )
            output_dir = tada / "results" / "strategy-brief"
            research_agent = _FakeMissingResearchAgent()
            build_agent = _FakeMissingResearchAgent()

            with patch.object(execute, "build_agent", side_effect=[(research_agent, None), (build_agent, None)]), \
                 patch.object(execute, "verify_and_refine", return_value=True):
                success = execute.run(str(task_path), str(output_dir), str(logs), model="fake")

            self.assertFalse(success)
            self.assertFalse(output_dir.exists())
            self.assertEqual(len(research_agent.messages), 2)
            self.assertIn("research folder is not ready", research_agent.messages[1][0]["content"])
            self.assertEqual(len(build_agent.messages), 0)

    def test_discover_and_promote_with_fake_agents(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            logs.mkdir()
            screen = logs / "screen"
            screen.mkdir()
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 0, 0), "screen", "reading papers") + "\n"
            )
            draft_state_json = "```json\n" + json.dumps({"upserts": [_candidate()], "rejected": [], "remove": [], "notes": ""}) + "\n```"
            reconcile_json = "```json\n" + json.dumps({"candidates": [_candidate()], "updates": [], "rejected": [], "notes": ""}) + "\n```"
            promotion_json = '```json\n{"ranked":[{"id":"paper-digest","score":9,"reason":"useful"}],"rejected":[]}\n```'
            discover_structured = _FakeStructuredCompletion(draft_state_json, reconcile_json)
            promote_structured = _FakeStructuredCompletion(promotion_json)

            fake_agent = _FakeToolAgent()
            with patch.object(discover, "build_agent", return_value=(fake_agent, None)), \
                 patch.object(discover, "structured_completion", side_effect=discover_structured):
                discover.run(str(logs), model="fake")
            discover_prompt = fake_agent.messages[0][0]["content"]
            self.assertIn("screen/filtered.jsonl", discover_prompt)
            self.assertIn("reading papers", discover_prompt)
            self.assertIn("(no drafts yet)", discover_prompt)
            self.assertIn("Idea Cards From This Chunk", discover_structured.instructions[0])
            self.assertIn("Draft Candidates From Discovery", discover_structured.instructions[1])
            candidate_files = sorted((logs / "moments" / "candidates").glob("*.jsonl"))
            self.assertEqual(len(candidate_files), 1)
            self.assertTrue((logs / "moments" / ".last_discovery").exists())

            with patch.object(promote, "structured_completion", side_effect=promote_structured):
                promote.run(str(logs), model="fake")
            accepted = root / "logs-tada" / "research" / "paper-digest.md"
            self.assertTrue(accepted.exists())
            self.assertIn("cadence: scheduled", accepted.read_text())
            self.assertIn("paper-digest", promote_structured.instructions[0])

    def test_invalid_discovery_does_not_write_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 0, 0), "screen", "reading papers") + "\n"
            )
            structured = _FakeStructuredCompletion("not json")
            with patch.object(discover, "build_agent", return_value=(_FakeToolAgent("not json"), None)), \
                 patch.object(discover, "structured_completion", side_effect=structured):
                with self.assertRaises(CandidateError):
                    discover.run(str(logs), model="fake")
            self.assertFalse((logs / "moments" / ".last_discovery").exists())

    def test_first_discovery_uses_recent_activity_window(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 10, 0), "screen", "ancient topic") + "\n"
                + _filtered_row(datetime(2025, 1, 3, 10, 0), "screen", "recent topic") + "\n"
            )
            structured = _FakeStructuredCompletion(
                "```json\n" + json.dumps({"upserts": [_candidate()], "rejected": [], "remove": [], "notes": ""}) + "\n```",
                "```json\n" + json.dumps({"candidates": [_candidate()], "updates": [], "rejected": [], "notes": ""}) + "\n```",
            )
            fake_agent = _FakeToolAgent()

            with patch.object(discover, "build_agent", return_value=(fake_agent, None)), \
                 patch.object(discover, "structured_completion", side_effect=structured):
                result = discover.run(str(logs), model="fake")

            discover_prompt = fake_agent.messages[0][0]["content"]
            self.assertIn("Activity window starts after: **2025-01-02 10:00**", discover_prompt)
            self.assertIn("recent topic", discover_prompt)
            self.assertNotIn("ancient topic", discover_prompt)
            self.assertIn("Activity window starts after: 2025-01-02 10:00", result)

    def test_discovery_retries_malformed_json_once(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 0, 0), "screen", "reading papers") + "\n"
            )
            structured = _FakeStructuredCompletion(
                StructuredOpsError("structured output validation failed"),
                "```json\n" + json.dumps({"upserts": [_candidate()], "rejected": [], "remove": [], "notes": ""}) + "\n```",
                "```json\n" + json.dumps({"candidates": [_candidate()], "updates": [], "rejected": [], "notes": ""}) + "\n```",
            )

            with patch.object(discover, "build_agent", return_value=(_FakeToolAgent(), None)), \
                 patch.object(discover, "structured_completion", side_effect=structured):
                discover.run(str(logs), model="fake")

            self.assertTrue((logs / "moments" / ".last_discovery").exists())
            candidate_files = sorted((logs / "moments" / "candidates").glob("*.jsonl"))
            self.assertEqual(len(candidate_files), 1)

    def test_discovery_reports_draft_compile_rejections(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 0, 0), "screen", "reading papers") + "\n"
            )
            structured = _FakeStructuredCompletion(
                "```json\n"
                + json.dumps({
                    "upserts": [],
                    "rejected": [{"id": "paper-digest", "reason": "too weak"}],
                    "remove": [],
                    "notes": "dropped weak idea",
                })
                + "\n```",
            )

            with patch.object(discover, "build_agent", return_value=(_FakeToolAgent(), None)), \
                 patch.object(discover, "structured_completion", side_effect=structured):
                result = discover.run(str(logs), model="fake")

            self.assertIn("Rejected or merged 1 drafts", result)
            self.assertTrue((logs / "moments" / ".last_discovery").exists())

    def test_structured_completion_accepts_provider_rejected_but_valid_pydantic_json(self):
        raw = json.dumps({"upserts": [_candidate()], "notes": ""})

        class _FakeSchemaError(Exception):
            raw_response = raw

        with patch.object(structured_completion_module.litellm, "JSONSchemaValidationError", _FakeSchemaError), \
             patch.object(structured_completion_module, "_litellm_structured_completion", side_effect=_FakeSchemaError()):
            text, payload = structured_completion_module.structured_completion(
                model="fake",
                instruction="instruction",
                response_model=DraftActionPayload,
            )

        self.assertEqual(text, raw)
        self.assertEqual(payload.upserts[0].slug, "paper-digest")
        self.assertEqual(payload.rejected, [])

    def test_promotion_retries_malformed_json_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            logs.mkdir()
            write_candidates_jsonl(logs, [validate_candidate(_candidate())])
            structured = _FakeStructuredCompletion(
                StructuredOpsError("structured output validation failed"),
                '```json\n{"ranked":[{"id":"paper-digest","score":9,"reason":"useful"}],"rejected":[]}\n```',
            )

            with patch.object(promote, "structured_completion", side_effect=structured):
                promote.run(str(logs), model="fake")

            self.assertTrue((logs / "moments" / ".last_promotion").exists())
            accepted = root / "logs-tada" / "research" / "paper-digest.md"
            self.assertTrue(accepted.exists())

    def test_promotion_routes_same_slug_to_existing_topic(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            logs.mkdir()
            tada = root / "logs-tada"
            accepted_dir = tada / "research"
            accepted_dir.mkdir(parents=True)
            (accepted_dir / "paper-digest.md").write_text(
                "---\n"
                "title: Paper Digest\n"
                "description: Track relevant papers.\n"
                "cadence: scheduled\n"
                "schedule: daily at 8am\n"
                "confidence: 0.80\n"
                "usefulness: 8\n"
                "---\n\nExisting body\n"
            )
            (tada / "results" / "paper-digest").mkdir(parents=True)
            write_candidates_jsonl(logs, [
                validate_candidate(
                    _candidate(
                        id="paper-digest-update",
                        slug="paper-digest",
                        topic="wrong-topic",
                        title="Updated Paper Digest",
                        evidence=["new evidence"],
                    )
                )
            ])
            structured = _FakeStructuredCompletion('```json\n{"ranked":[{"id":"paper-digest-update","score":9,"reason":"useful update"}],"rejected":[]}\n```')

            with patch.object(promote, "structured_completion", side_effect=structured):
                result = promote.run(str(logs), model="fake")

            accepted = accepted_dir / "paper-digest.md"
            accepted_text = accepted.read_text()
            self.assertIn("Updated Paper Digest", accepted_text)
            self.assertIn("new evidence", accepted_text)
            self.assertFalse((tada / "wrong-topic" / "paper-digest.md").exists())
            self.assertIn('"topic": "research"', structured.instructions[0])
            self.assertNotIn('"topic": "wrong-topic"', structured.instructions[0])
            self.assertIn("Routed 1 same-slug candidates", result)

    def test_promotion_ranks_all_candidates_then_promotes_top_k(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            logs.mkdir()
            first = validate_candidate(_candidate(id="first", slug="first", title="First"))
            second = validate_candidate(_candidate(id="second", slug="second", title="Second"))
            third = validate_candidate(_candidate(id="third", slug="third", title="Third"))
            write_candidates_jsonl(logs, [first, second, third])
            structured = _FakeStructuredCompletion(
                "```json\n"
                + json.dumps({
                    "ranked": [
                        {"id": "third", "score": 10, "reason": "best"},
                        {"id": "first", "score": 8, "reason": "next"},
                        {"id": "second", "score": 6, "reason": "viable"},
                    ],
                    "rejected": [],
                })
                + "\n```"
            )

            with patch.object(promote, "structured_completion", side_effect=structured):
                result = promote.run(str(logs), model="fake", n=2)

            self.assertIn('"slug": "second"', structured.instructions[0])
            self.assertTrue((root / "logs-tada" / "research" / "third.md").exists())
            self.assertTrue((root / "logs-tada" / "research" / "first.md").exists())
            self.assertFalse((root / "logs-tada" / "research" / "second.md").exists())
            self.assertIn("Ranked 3 of 3 candidates. Promoted top 2", result)

    def test_chronological_merge_skips_checkpoint_and_invalid_rows(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            email = logs / "email"
            screen.mkdir(parents=True)
            email.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                "\n".join(
                    [
                        _filtered_row(datetime(2025, 1, 1, 10, 0), "screen", "old topic"),
                        json.dumps({"text": "missing timestamp"}),
                        _filtered_row(datetime(2025, 1, 3, 10, 0), "screen", "screen topic"),
                    ]
                )
                + "\n"
            )
            (email / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 2, 10, 0), "email", "email topic") + "\n"
            )

            rows = list(discover._merged_filtered_rows(logs, datetime(2025, 1, 1, 12, 0)))

            self.assertEqual([row.source_name for row in rows], ["email", "screen"])
            self.assertEqual([row.entry["text"] for row in rows], ["email topic", "screen topic"])

    def test_connector_aware_rendering(self):
        screen = discover.FilteredRow(
            timestamp=datetime(2025, 1, 1, 10, 0),
            timestamp_value=datetime(2025, 1, 1, 10, 0).timestamp(),
            rel_path="screen/filtered.jsonl",
            line_no=3,
            source_name="screen",
            entry={
                "timestamp": datetime(2025, 1, 1, 10, 0).timestamp(),
                "text": "reviewing PR",
                "dense_caption": "GitHub pull request visible",
                "img_path": "/tmp/screen.png",
                "source": {"id": "row-id", "screenshot_path": "/tmp/shot.png", "raw_events": [{"x": 1}]},
            },
        )
        calendar = discover.FilteredRow(
            timestamp=datetime(2025, 1, 1, 11, 0),
            timestamp_value=datetime(2025, 1, 1, 11, 0).timestamp(),
            rel_path="calendar/filtered.jsonl",
            line_no=1,
            source_name="calendar",
            entry={
                "timestamp": datetime(2025, 1, 1, 11, 0).timestamp(),
                "text": "",
                "source": {
                    "summary": "Project sync",
                    "start": {"dateTime": "2025-01-01T11:00:00"},
                    "end": {"dateTime": "2025-01-01T11:30:00"},
                    "location": "Zoom",
                },
            },
        )

        screen_text = discover._render_filtered_row(screen)
        calendar_text = discover._render_filtered_row(calendar)

        self.assertIn("source.id: row-id", screen_text)
        self.assertIn("dense_caption: GitHub pull request visible", screen_text)
        self.assertIn("source.screenshot_path: /tmp/shot.png", screen_text)
        self.assertNotIn("raw_events", screen_text)
        self.assertIn("text: Project sync", calendar_text)
        self.assertIn("source.start: 2025-01-01T11:00:00", calendar_text)
        self.assertIn("source.location: Zoom", calendar_text)

    def test_chunking_respects_target_overlap_and_order(self):
        rows = []
        for i in range(6):
            rows.append(
                discover.FilteredRow(
                    timestamp=datetime(2025, 1, 1, 10, i),
                    timestamp_value=datetime(2025, 1, 1, 10, i).timestamp(),
                    rel_path="screen/filtered.jsonl",
                    line_no=i + 1,
                    source_name="screen",
                    entry={"timestamp": datetime(2025, 1, 1, 10, i).timestamp(), "text": f"topic {i}", "source": {}},
                )
            )

        chunks = list(discover._chunk_filtered_rows(iter(rows), target_chars=210, overlap_chars=90))

        self.assertGreater(len(chunks), 1)
        flattened_times = [rendered.row.timestamp for chunk in chunks for rendered in chunk.rows]
        self.assertEqual(flattened_times, sorted(flattened_times))
        self.assertEqual(chunks[0].rows[-1].row.line_no, chunks[1].rows[0].row.line_no)

    def test_discover_multiple_chunks_reconciles_parallel_chunk_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 10, 0), "screen", "reading papers") + "\n"
            )
            row1 = discover.RenderedRow(
                row=discover.FilteredRow(
                    timestamp=datetime(2025, 1, 1, 10, 0),
                    timestamp_value=datetime(2025, 1, 1, 10, 0).timestamp(),
                    rel_path="screen/filtered.jsonl",
                    line_no=1,
                    source_name="screen",
                    entry={},
                ),
                text="time: 2025-01-01 10:00:00\nsource: screen\ntext: reading papers",
            )
            row2 = discover.RenderedRow(
                row=discover.FilteredRow(
                    timestamp=datetime(2025, 1, 1, 10, 5),
                    timestamp_value=datetime(2025, 1, 1, 10, 5).timestamp(),
                    rel_path="screen/filtered.jsonl",
                    line_no=2,
                    source_name="screen",
                    entry={},
                ),
                text="time: 2025-01-01 10:05:00\nsource: screen\ntext: organizing papers",
            )
            first = _candidate(title="Paper Digest", evidence=["first chunk"])
            second = _candidate(title="Paper Digest", evidence=["first chunk", "second chunk"])
            structured = _FakeStructuredCompletion(
                "```json\n" + json.dumps({"upserts": [first], "rejected": [], "remove": [], "notes": ""}) + "\n```",
                "```json\n" + json.dumps({"upserts": [second], "rejected": [], "remove": [], "notes": ""}) + "\n```",
                "```json\n" + json.dumps({"candidates": [second], "updates": [], "rejected": [], "notes": "kept final draft"}) + "\n```",
            )
            fake_agent = _FakeToolAgent(
                "```json\n" + json.dumps({"ideas": [_idea(evidence=["first chunk"])], "notes": ""}) + "\n```",
                "```json\n" + json.dumps({"ideas": [_idea(evidence=["second chunk"], relation_to_existing="possible_update")], "notes": ""}) + "\n```",
            )
            chunks = [discover.ActivityChunk(index=1, rows=[row1]), discover.ActivityChunk(index=2, rows=[row2])]

            with patch.object(discover, "build_agent", return_value=(fake_agent, None)), \
                 patch.object(discover, "_chunk_filtered_rows", return_value=iter(chunks)), \
                 patch.object(discover, "structured_completion", side_effect=structured):
                discover.run(str(logs), model="fake")

            compile_instructions = [
                instruction for instruction in structured.instructions
                if "Idea Cards From This Chunk" in instruction
            ]
            reconcile_instructions = [
                instruction for instruction in structured.instructions
                if "Draft Candidates From Discovery" in instruction
            ]
            self.assertEqual(len(compile_instructions), 2)
            self.assertEqual(len(reconcile_instructions), 1)
            self.assertTrue(any("second chunk" in instruction for instruction in compile_instructions))
            candidate_file = sorted((logs / "moments" / "candidates").glob("*.jsonl"))[-1]
            self.assertIn("second chunk", candidate_file.read_text())

    def test_reconciliation_routes_duplicate_as_update(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 10, 0), "screen", "reading papers") + "\n"
            )
            tada = root / "logs-tada"
            accepted_dir = tada / "research"
            accepted_dir.mkdir(parents=True)
            (accepted_dir / "paper-digest.md").write_text(
                "---\n"
                "title: Paper Digest\n"
                "description: Track relevant papers.\n"
                "cadence: scheduled\n"
                "schedule: daily at 8am\n"
                "confidence: 0.80\n"
                "usefulness: 8\n"
                "---\n\nExisting body\n"
            )
            (tada / "results" / "paper-digest").mkdir(parents=True)
            draft = _candidate(id="new-paper-tracker", slug="new-paper-tracker", evidence=["new evidence"])
            update = _candidate(id="paper-digest", slug="paper-digest", evidence=["new evidence"])
            structured = _FakeStructuredCompletion(
                "```json\n" + json.dumps({"upserts": [draft], "rejected": [], "remove": [], "notes": ""}) + "\n```",
                "```json\n"
                + json.dumps({
                    "candidates": [update],
                    "updates": [{"candidate_id": "new-paper-tracker", "accepted_slug": "paper-digest", "reason": "same recurring paper workflow"}],
                    "rejected": [],
                    "notes": "routed duplicate as update",
                })
                + "\n```",
            )

            with patch.object(discover, "build_agent", return_value=(_FakeToolAgent(), None)), \
                 patch.object(discover, "structured_completion", side_effect=structured):
                result = discover.run(str(logs), model="fake")

            self.assertIn("research/paper-digest", structured.instructions[1])
            self.assertIn("Routed 1 candidates as updates", result)
            candidate_file = sorted((logs / "moments" / "candidates").glob("*.jsonl"))[-1]
            candidate_text = candidate_file.read_text()
            self.assertIn('"slug": "paper-digest"', candidate_text)
            self.assertNotIn("new-paper-tracker", candidate_text)


if __name__ == "__main__":
    unittest.main()
