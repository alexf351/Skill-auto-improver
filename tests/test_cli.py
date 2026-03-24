from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.cli import main, evaluate_skill_fixtures
from skill_auto_improver.evaluator import GoldenFixture


class CLITests(unittest.TestCase):
    def _write_fixture_file(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                [
                    {
                        "name": "formal_greeting_present",
                        "input_data": {"path": "SKILL.md"},
                        "expected_output": {
                            "contains": ["Use the formal greeting."],
                            "not_contains": ["Do not use the formal greeting."],
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )

    def test_trial_command_accepts_safe_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)

            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["accepted"])
            self.assertFalse(payload["rolled_back"])
            self.assertEqual(payload["ab"]["recovered_count"], 1)
            self.assertIn("Use the formal greeting.", (skill_dir / "SKILL.md").read_text(encoding="utf-8"))

    def test_trial_command_rolls_back_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            original = "# Demo Skill\n\nUse the formal greeting.\n"
            (skill_dir / "SKILL.md").write_text(original, encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Break the working instruction", "content": {"suggestion": "Do not use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertFalse(payload["accepted"])
            self.assertTrue(payload["rolled_back"])
            self.assertEqual(payload["ab"]["regressed_count"], 1)
            self.assertEqual((skill_dir / "SKILL.md").read_text(encoding="utf-8"), original)

    def test_trial_command_respects_min_confidence_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            original = "# Demo Skill\n"
            (skill_dir / "SKILL.md").write_text(original, encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path), "--min-confidence", "0.9"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertFalse(payload["accepted"])
            self.assertTrue(payload["rolled_back"] is False)
            self.assertEqual(payload["apply"]["applied_count"], 0)
            self.assertEqual(payload["ab"]["recovered_count"], 0)
            self.assertEqual(payload["acceptance_reason"], "no proposals applied")
            self.assertIn("below minimum", payload["apply"]["skipped"][0]["detail"])
            self.assertEqual((skill_dir / "SKILL.md").read_text(encoding="utf-8"), original)

    def test_trial_command_uses_memory_policy_when_cli_threshold_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            (skill_dir / "data").mkdir()
            (skill_dir / "data" / "preferences.json").write_text(json.dumps({"proposal": {"min_confidence": 0.9}}), encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["policy"]["min_confidence"], 0.9)
            self.assertEqual(payload["apply"]["applied_count"], 0)
            self.assertEqual(payload["acceptance_reason"], "no proposals applied")

    def test_trial_command_uses_fixture_level_memory_policy_when_cli_threshold_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            (skill_dir / "data").mkdir()
            (skill_dir / "data" / "preferences.json").write_text(json.dumps({
                "proposal": {
                    "fixture_policies": {
                        "formal_greeting_present": {
                            "min_confidence": 0.9,
                            "accepted_severities": ["critical"]
                        }
                    }
                }
            }), encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["apply"]["applied_count"], 0)
            self.assertIn("below minimum 0.90", payload["apply"]["skipped"][0]["detail"])
            self.assertEqual(payload["policy"]["fixture_policies"]["formal_greeting_present"]["accepted_severities"], ["critical"])

    def test_trial_command_can_persist_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")
            logs_dir = root / "runs"

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path), "--logs-dir", str(logs_dir)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertIn("trace_path", payload)
            trace_path = Path(payload["trace_path"])
            self.assertTrue(trace_path.exists())
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual(trace["status"], "ok")
            self.assertEqual([step["name"] for step in trace["steps"]], ["before_eval", "apply_trial", "after_eval"])
            self.assertEqual(trace["metadata"]["patch_trial"]["accepted"], True)
            self.assertEqual(trace["metadata"]["patch_trial"]["recovered_count"], 1)
            self.assertEqual(trace["metadata"]["cli"]["command"], "trial")

    def test_evaluate_skill_fixtures_supports_command_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()

            outputs = evaluate_skill_fixtures(
                str(skill_dir),
                [
                    GoldenFixture(
                        name="command_probe",
                        input_data={"command": ["python3", "-c", "print('formal greeting ok')"]},
                        expected_output={
                            "exit_code": 0,
                            "stdout_contains": ["formal greeting ok"],
                            "stdout_not_contains": ["error"],
                            "stderr_contains": [],
                            "stderr_not_contains": ["Traceback"],
                        },
                    )
                ],
            )
            self.assertEqual(outputs["command_probe"]["exit_code"], 0)
            self.assertEqual(outputs["command_probe"]["stdout_contains"], ["formal greeting ok"])
            self.assertEqual(outputs["command_probe"]["stdout_not_contains"], ["error"])
            self.assertEqual(outputs["command_probe"]["stderr_not_contains"], ["Traceback"])

    def test_trial_command_supports_command_based_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            script_path = skill_dir / "check_skill.py"
            script_path.write_text(
                "from pathlib import Path\n"
                "content = Path('SKILL.md').read_text(encoding='utf-8')\n"
                "print('formal greeting ok' if 'Use the formal greeting.' in content else 'formal greeting missing')\n",
                encoding="utf-8",
            )
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "command_probe",
                            "input_data": {"command": ["python3", "check_skill.py"]},
                            "expected_output": {
                                "exit_code": 0,
                                "stdout_contains": ["formal greeting ok"],
                                "stdout_not_contains": ["formal greeting missing"],
                                "stderr_contains": [],
                                "stderr_not_contains": ["Traceback"],
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "command_probe", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["stdout_contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["accepted"])
            self.assertEqual(payload["ab"]["recovered_count"], 1)
            self.assertIn("Use the formal greeting.", (skill_dir / "SKILL.md").read_text(encoding="utf-8"))

    def test_inspect_backups_command_returns_diff_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])
            skill_md.write_text("# Demo Skill\n\nBROKEN\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["inspect-backups", "--skill-path", str(skill_dir), "--limit", "1", "--target-name", "SKILL.md"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["backup_count"], 1)
            self.assertEqual(len(payload["backups"]), 1)
            self.assertTrue(payload["backups"][0]["current_exists"])
            self.assertGreater(payload["backups"][0]["current_diff"]["added_lines"], 0)
            self.assertTrue(any("BROKEN" in line for line in payload["backups"][0]["current_diff"]["preview"]))

    def test_restore_backup_command_accepts_backup_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])
            trial_payload = json.loads(stdout.getvalue())
            backup_id = trial_payload["apply"]["applied"][0]["backup_id"]
            skill_md.write_text("BROKEN\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["restore-backup", "--skill-path", str(skill_dir), "--backup", backup_id, "--target-name", "SKILL.md"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["restored"])
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "# Demo Skill\n")

    def test_backup_history_command_returns_trial_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["backup-history", "--skill-path", str(skill_dir), "--limit", "1"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(payload["recent_trials"]), 1)
            self.assertIn("backup_summary", payload)
            self.assertIn("operating_memory", payload)

    def test_restore_latest_backup_command_restores_newest_target_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([{ "fixture_name": "formal_greeting_present", "type": "instruction", "description": "Add the formal greeting guidance", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["contains"]}, "severity": "warning", "confidence": 0.85 }]), encoding="utf-8")

            main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])
            skill_md.write_text("# Demo Skill\n\nsecond version\n", encoding="utf-8")
            main(["trial", "--skill-path", str(skill_dir), "--fixtures", str(fixtures_path), "--proposals", str(proposals_path)])
            skill_md.write_text("BROKEN\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["restore-latest-backup", "--skill-path", str(skill_dir), "--target-name", "SKILL.md"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["restored"])
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "# Demo Skill\n\nsecond version\n")

    def test_restore_latest_backup_command_returns_failure_when_target_has_no_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["restore-latest-backup", "--skill-path", str(skill_dir), "--target-name", "golden-fixtures.json"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertFalse(payload["restored"])
            self.assertIn("no backups found", payload["detail"])


if __name__ == "__main__":
    unittest.main()
