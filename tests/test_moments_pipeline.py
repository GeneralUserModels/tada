from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apps.moments.steps import discover, promote
from apps.moments.core.candidates import (
    CandidateError,
    parse_discovery_result,
    parse_promotion_result,
    render_accepted_markdown,
    validate_candidate,
)
from apps.moments.core.paths import migrate_moments_to_cadence
from apps.moments.runtime.scheduler import should_run


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


class _FakeAgent:
    def __init__(self, result: str):
        self.result = result
        self.max_rounds = 0
        self.on_round = None
        self.messages = []

    def run(self, messages):
        self.messages = messages
        return self.result


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
            '```json\n{"promoted":["paper-digest"],"rejected":[]}\n```',
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
            discovery_json = "```json\n" + json.dumps({"create": [_candidate()], "update": [], "merge": [], "reject": [], "notes": ""}) + "\n```"
            reconcile_json = "```json\n" + json.dumps({"candidates": [_candidate()], "updates": [], "rejected": [], "notes": ""}) + "\n```"
            promotion_json = '```json\n{"promoted":["paper-digest"],"rejected":[]}\n```'
            discover_agent = _FakeAgent(discovery_json)
            reconcile_agent = _FakeAgent(reconcile_json)
            promote_agent = _FakeAgent(promotion_json)

            with patch.object(discover, "build_agent", side_effect=[(discover_agent, None), (reconcile_agent, None)]):
                discover.run(str(logs), model="fake")
            discover_prompt = discover_agent.messages[0]["content"]
            self.assertIn("screen/filtered.jsonl", discover_prompt)
            self.assertIn("reading papers", discover_prompt)
            self.assertIn("(no drafts yet)", discover_prompt)
            self.assertIn("Draft Candidates From Discovery", reconcile_agent.messages[0]["content"])
            candidate_files = sorted((logs / "moments" / "candidates").glob("*.jsonl"))
            self.assertEqual(len(candidate_files), 1)
            self.assertTrue((logs / "moments" / ".last_discovery").exists())

            with patch.object(promote, "build_agent", return_value=(promote_agent, None)):
                promote.run(str(logs), model="fake")
            accepted = root / "logs-tada" / "research" / "paper-digest.md"
            self.assertTrue(accepted.exists())
            self.assertIn("cadence: scheduled", accepted.read_text())
            self.assertIn("paper-digest", promote_agent.messages[0]["content"])

    def test_invalid_discovery_does_not_write_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            screen = logs / "screen"
            screen.mkdir(parents=True)
            (screen / "filtered.jsonl").write_text(
                _filtered_row(datetime(2025, 1, 1, 0, 0), "screen", "reading papers") + "\n"
            )
            agent = _FakeAgent("not json")
            with patch.object(discover, "build_agent", return_value=(agent, None)):
                with self.assertRaises(CandidateError):
                    discover.run(str(logs), model="fake")
            self.assertFalse((logs / "moments" / ".last_discovery").exists())

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

    def test_discover_multiple_chunks_carries_drafts_forward(self):
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
            agents = [
                _FakeAgent("```json\n" + json.dumps({"create": [first], "update": [], "merge": [], "reject": [], "notes": ""}) + "\n```"),
                _FakeAgent(
                    "```json\n"
                    + json.dumps({
                        "create": [],
                        "update": [{"id": "paper-digest", "fields": {"evidence": ["first chunk", "second chunk"]}}],
                        "merge": [],
                        "reject": [],
                        "notes": "",
                    })
                    + "\n```"
                ),
                _FakeAgent("```json\n" + json.dumps({"candidates": [second], "updates": [], "rejected": [], "notes": "kept final draft"}) + "\n```"),
            ]
            chunks = [discover.ActivityChunk(index=1, rows=[row1]), discover.ActivityChunk(index=2, rows=[row2])]

            with patch.object(discover, "_chunk_filtered_rows", return_value=iter(chunks)), patch.object(discover, "build_agent", side_effect=[(agents[0], None), (agents[1], None), (agents[2], None)]):
                discover.run(str(logs), model="fake")

            self.assertIn("Paper Digest", agents[1].messages[0]["content"])
            self.assertIn("second chunk", agents[2].messages[0]["content"])
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
            discovery_agent = _FakeAgent("```json\n" + json.dumps({"create": [draft], "update": [], "merge": [], "reject": [], "notes": ""}) + "\n```")
            reconcile_agent = _FakeAgent(
                "```json\n"
                + json.dumps({
                    "candidates": [update],
                    "updates": [{"candidate_id": "new-paper-tracker", "accepted_slug": "paper-digest", "reason": "same recurring paper workflow"}],
                    "rejected": [],
                    "notes": "routed duplicate as update",
                })
                + "\n```"
            )

            with patch.object(discover, "build_agent", side_effect=[(discovery_agent, None), (reconcile_agent, None)]):
                result = discover.run(str(logs), model="fake")

            self.assertIn("research/paper-digest", reconcile_agent.messages[0]["content"])
            self.assertIn("Routed 1 candidates as updates", result)
            candidate_file = sorted((logs / "moments" / "candidates").glob("*.jsonl"))[-1]
            candidate_text = candidate_file.read_text()
            self.assertIn('"slug": "paper-digest"', candidate_text)
            self.assertNotIn("new-paper-tracker", candidate_text)


if __name__ == "__main__":
    unittest.main()
