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

from apps.memory import ingest


def _write_checkpoint(path: Path, value: str = "2025-01-01T00:00:00") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n")


class MemoryIngestTests(unittest.TestCase):
    def test_collect_inputs_classifies_first_incremental_and_no_new_data(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            logs.mkdir()
            ingest._bootstrap_memory(logs / "memory")

            first = ingest._collect_ingest_inputs(logs, None)
            self.assertEqual(first.mode, "first_run")

            _write_checkpoint(logs / "memory" / ".last_ingest")
            chat = logs / "chats" / "chat_1" / "conversation.md"
            chat.parent.mkdir(parents=True)
            chat.write_text("**User:** hello\n")
            session = logs / "session_20250102_000000"
            session.mkdir()
            (session / "labels.jsonl").write_text(
                json.dumps({"start_time": "2025-01-02_00-00-00-000000", "text": "coding"}) + "\n"
            )

            incremental = ingest._collect_ingest_inputs(logs, datetime(2025, 1, 1))
            self.assertEqual(incremental.mode, "incremental")
            self.assertIn("chats/chat_1/conversation.md", incremental.new_inputs_list)
            self.assertIn("session_20250102_000000/labels.jsonl", incremental.new_inputs_list)

            no_new = ingest._collect_ingest_inputs(logs, datetime(2099, 1, 1))
            self.assertEqual(no_new.mode, "no_new_data")
            self.assertEqual(no_new.new_inputs_list, "- (none detected)")

    def test_bootstrap_creates_special_files_without_overwriting(self):
        with tempfile.TemporaryDirectory() as d:
            memory = Path(d) / "logs" / "memory"
            memory.mkdir(parents=True)
            (memory / "index.md").write_text("existing index")
            (memory / "log.md").write_text("existing log")

            ingest._bootstrap_memory(memory)

            self.assertEqual((memory / "index.md").read_text(), "existing index")
            self.assertEqual((memory / "log.md").read_text(), "existing log")
            self.assertIn("Memory Wiki Schema", (memory / "schema.md").read_text())

    def test_validation_detects_frontmatter_index_and_log_issues(self):
        with tempfile.TemporaryDirectory() as d:
            memory = Path(d) / "logs" / "memory"
            ingest._bootstrap_memory(memory)
            (memory / "project.md").write_text("# Project\n")
            (memory / ".hidden.md").write_text("# Hidden\n")

            issues = ingest._validate_wiki(memory, "2026-05-03")
            codes = {issue["code"] for issue in issues}

            self.assertIn("missing_frontmatter", codes)
            self.assertIn("index_missing_page", codes)
            self.assertIn("missing_log_entry", codes)
            self.assertFalse(any(issue["path"] == ".hidden.md" for issue in issues))

    def test_run_executes_three_passes_and_writes_checkpoint_after_finalize(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            logs.mkdir()
            calls: list[tuple[str, str]] = []

            def fake_pass(pass_name, instruction, logs_dir, model, api_key, on_round, subagent_model, subagent_api_key):
                calls.append((pass_name, instruction))
                memory = Path(logs_dir) / "memory"
                if pass_name == "inventory":
                    return """```json
{"mode":"first_run","sources_to_read":[],"existing_pages_to_read":[],"likely_pages_to_create":["Project"],"likely_pages_to_update":[],"backfill_sources_to_sample":[],"rationale":"test"}
```"""
                if pass_name == "update":
                    self.assertIn('"likely_pages_to_create"', instruction)
                    (memory / "project.md").write_text(
                        "---\ntitle: Project\nconfidence: 0.7\nlast_updated: 2026-05-03\n---\n\nProject page. [c:0.7]\n"
                    )
                    return "updated project.md"
                if pass_name == "finalize":
                    today = datetime.now().strftime("%Y-%m-%d")
                    (memory / "index.md").write_text("# Memory Index\n\n- Project — project.md\n")
                    (memory / "log.md").write_text(f"# Memory Log\n\n## {today}\n- Created [[Project]].\n")
                    return "finalized"
                raise AssertionError(pass_name)

            with patch.object(ingest, "_run_agent_pass", side_effect=fake_pass):
                result = ingest.run(str(logs), model="fake-model")

            self.assertEqual([name for name, _ in calls], ["inventory", "update", "finalize"])
            self.assertTrue((logs / "memory" / ".last_ingest").exists())
            self.assertIn("## Inventory", result)
            self.assertIn("updated project.md", result)

    def test_run_does_not_checkpoint_on_bad_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            logs.mkdir()

            with patch.object(ingest, "_run_agent_pass", return_value="no json"):
                with self.assertRaises(ValueError):
                    ingest.run(str(logs), model="fake-model")

            self.assertFalse((logs / "memory" / ".last_ingest").exists())

    def test_run_does_not_checkpoint_when_final_validation_fails(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            logs.mkdir()

            def fake_pass(pass_name, instruction, logs_dir, model, api_key, on_round, subagent_model, subagent_api_key):
                memory = Path(logs_dir) / "memory"
                if pass_name == "inventory":
                    return """```json
{"mode":"first_run","sources_to_read":[],"existing_pages_to_read":[],"likely_pages_to_create":["Project"],"likely_pages_to_update":[],"backfill_sources_to_sample":[],"rationale":"test"}
```"""
                if pass_name == "update":
                    (memory / "project.md").write_text("Project page without frontmatter.\n")
                    return "updated"
                return "did not repair index or log"

            with patch.object(ingest, "_run_agent_pass", side_effect=fake_pass):
                with self.assertRaises(RuntimeError):
                    ingest.run(str(logs), model="fake-model")

            self.assertFalse((logs / "memory" / ".last_ingest").exists())

    def test_validation_checks_all_memory_pages_for_index_entries(self):
        with tempfile.TemporaryDirectory() as d:
            memory = Path(d) / "logs" / "memory"
            ingest._bootstrap_memory(memory)
            (memory / "project.md").write_text(
                "---\ntitle: Project\nconfidence: 0.7\nlast_updated: 2026-05-03\n---\n\nProject page.\n"
            )
            (memory / "person.md").write_text(
                "---\ntitle: Person\nconfidence: 0.7\nlast_updated: 2026-05-03\n---\n\nPerson page.\n"
            )
            (memory / "index.md").write_text("# Memory Index\n\n- Project — project.md\n")
            (memory / "log.md").write_text("## 2026-05-03\n- Updated Project.\n")
            today = "2026-05-03"

            issues = ingest._validate_wiki(memory, today)

            self.assertIn(
                {"code": "index_missing_page", "path": "person.md", "message": "Content page is not represented in index.md by path or title"},
                issues,
            )

    def test_update_prompt_includes_update_rules_without_stage_label(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            memory = logs / "memory"
            ingest._bootstrap_memory(memory)
            inputs = ingest.IngestInputs(
                mode="incremental",
                last_ingest=datetime(2025, 1, 1),
                new_inputs_list="- chats/chat_1/conversation.md",
                active_conversations=[],
                chats=[],
                audio=[],
                tada_feedback=[],
                sessions=[],
                modified_streams=[],
            )
            prompt = ingest._update_prompt(
                "2026-05-03 12:00",
                str(logs),
                memory,
                inputs,
                {
                    "mode": "incremental",
                    "sources_to_read": [],
                    "existing_pages_to_read": [],
                    "likely_pages_to_create": [],
                    "likely_pages_to_update": [],
                    "backfill_sources_to_sample": [],
                    "rationale": "test",
                },
            )

            self.assertIn("Output content-page changes only.", prompt)
            self.assertIn("Do not update `index.md`, `log.md`, or `schema.md`.", prompt)
            self.assertNotIn("You are doing the UPDATE pass", prompt)


if __name__ == "__main__":
    unittest.main()
