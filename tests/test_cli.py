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

    def test_compile_workspace_command_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["compile-workspace", "--skill-path", str(skill_dir)])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["skill_summary"]["skill_md_exists"])
            self.assertIn("open_questions", payload)
            self.assertIn("fixture_hotspots", payload["trace_summary"])

    def test_compile_workspace_command_can_render_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["compile-workspace", "--skill-path", str(skill_dir), "--markdown"])

            payload = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("# Trial Workspace", payload)
            self.assertIn("## Skill Summary", payload)

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

    def test_evaluate_skill_fixtures_rejects_command_probe_cwd_outside_skill_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()

            with self.assertRaisesRegex(ValueError, "input_data.cwd must stay inside the skill path"):
                evaluate_skill_fixtures(
                    str(skill_dir),
                    [
                        GoldenFixture(
                            name="command_probe",
                            input_data={"command": ["python3", "-c", "print('hi')"], "cwd": "../outside"},
                            expected_output={"exit_code": 0},
                        )
                    ],
                )

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

    def test_suggest_fixtures_command_returns_ranked_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            brain_dir.mkdir()
            from skill_auto_improver.shared_brain import SharedBrain

            brain = SharedBrain(brain_dir)
            brain.add_fixture_to_library(
                fixture_pattern_name="greeting_formal",
                fixture_template={"name": "greeting_formal", "expected_output": {"greeting": "Hello"}},
                expected_behavior="Formal greeting",
                successful_skills=["weather", "kiro"],
            )
            brain.add_fixture_to_library(
                fixture_pattern_name="farewell_formal",
                fixture_template={"name": "farewell_formal"},
                expected_behavior="Formal farewell",
                successful_skills=["weather"],
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["suggest-fixtures", "--brain-dir", str(brain_dir), "--fixture-name", "greeting_formal_check", "--limit", "1"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["suggestion_count"], 1)
            self.assertEqual(payload["suggestions"][0]["pattern_name"], "greeting_formal")
            self.assertIn("greeting", payload["suggestions"][0]["shared_traits"])
            self.assertEqual(payload["suggestions"][0]["fixture_template"]["name"], "greeting_formal")

    def test_brain_dashboard_command_returns_system_and_skill_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            brain_dir.mkdir()
            from skill_auto_improver.shared_brain import SharedBrain

            brain = SharedBrain(brain_dir)
            brain.record_promotion(
                fixture_name="weather_forecast_check",
                skill_name="weather",
                proposal_types=["test_case", "instruction"],
                reason="Recovered safely",
                confidence=0.91,
            )
            brain.record_regression(
                pattern_name="instruction_without_test",
                skill_name="weather",
                trigger="instruction only patch",
                fix_strategy="pair with test case",
                severity="critical",
            )
            brain.update_skill_mastery("weather", total_trials=6, successful_promotions=4)
            brain.add_fixture_to_library(
                fixture_pattern_name="weather_forecast",
                fixture_template={"name": "weather_forecast"},
                expected_behavior="Forecast stays structured",
                successful_skills=["weather"],
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["brain-dashboard", "--brain-dir", str(brain_dir), "--skill-name", "weather", "--limit", "1"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["counts"]["promotion_wisdom"], 1)
            self.assertEqual(payload["counts"]["regression_patterns"], 1)
            self.assertEqual(payload["top_promotions"][0]["fixture_name"], "weather_forecast_check")
            self.assertEqual(payload["top_regressions"][0]["pattern_name"], "instruction_without_test")
            self.assertEqual(payload["most_active_skills"][0]["skill_name"], "weather")
            self.assertEqual(payload["skill"]["skill_name"], "weather")
            self.assertEqual(payload["fixture_suggestions"][0]["pattern_name"], "weather_forecast")

    def test_run_orchestration_command_executes_batch_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "min_confidence": 0.91,
                    "accepted_severities": ["critical"],
                }
            ]), encoding="utf-8")
            logs_dir = root / "logs"

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                    "--logs-dir", str(logs_dir),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["skill_count"], 1)
            self.assertEqual(payload["run"]["total_skills"], 1)
            self.assertIn("demo_skill", payload["run"]["skill_outcomes"])
            self.assertTrue(any(logs_dir.glob("orchestration_*.json")))

    def test_run_orchestration_command_rejects_non_list_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps({"skill_path": "/tmp/demo"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

    def test_run_orchestration_command_rejects_invalid_entry_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": "/tmp/demo",
                    "skill_name": "demo_skill",
                    "min_confidence": 1.5,
                }
            ]), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "index 0"):
                main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

    def test_run_orchestration_command_reports_preflight_failures_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(root / "missing-fixtures.json"),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            outcome = payload["run"]["skill_outcomes"]["demo_skill"]
            self.assertEqual(outcome["status"], "error")
            self.assertFalse(outcome["preflight_ok"])
            self.assertEqual(outcome["preflight_issues"][0]["code"], "missing_fixtures")

    def test_run_orchestration_command_reports_semantic_fixture_preflight_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "bad_fixture",
                    "input_data": {"command": "python3 check.py", "path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issue = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"][0]
            self.assertEqual(issue["code"], "invalid_fixtures_shape")
            self.assertIn("exactly one of input_data.path or input_data.command", issue["message"])

    def test_run_orchestration_command_reports_artifact_target_preflight_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": "artifact",
                    "fixture_name": "greeting_test",
                    "confidence": 0.9,
                    "severity": "warning",
                    "content": {
                        "target_path": "../outside.md",
                        "body": "- Unsafe write",
                    },
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "proposals_path": str(proposals_path),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issue = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"][0]
            self.assertEqual(issue["code"], "invalid_proposals_shape")
            self.assertIn("escapes the skill root", issue["message"])

    def test_run_orchestration_command_reports_duplicate_fixture_name_preflight_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "greeting_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                },
                {
                    "name": "greeting_test",
                    "input_data": {"command": ["python3", "check.py"]},
                    "expected_output": {"stdout_contains": ["Hello"]},
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issue = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"][0]
            self.assertEqual(issue["code"], "invalid_fixtures_shape")
            self.assertIn("duplicates index 0", issue["message"])
            self.assertIn("proposal targeting ambiguous", issue["message"])

    def test_run_orchestration_command_reports_proposal_coverage_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "greeting_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                },
                {
                    "name": "farewell_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Bye"]},
                }
            ]), encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": "instruction",
                    "fixture_name": "greeting_test",
                    "confidence": 0.9,
                    "severity": "warning"
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                    "proposals_path": str(proposals_path),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issues = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"]
            coverage_issue = next(issue for issue in issues if issue["code"] == "proposal_coverage_gap")
            self.assertIn("fixtures without matching proposals", coverage_issue["message"])
            self.assertIn("farewell_test", coverage_issue["message"])

    def test_run_orchestration_command_reports_duplicate_proposal_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "greeting_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                }
            ]), encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": "instruction",
                    "fixture_name": "greeting_test",
                    "confidence": 0.9,
                    "severity": "warning"
                },
                {
                    "type": "instruction",
                    "fixture_name": "greeting_test",
                    "confidence": 0.95,
                    "severity": "critical"
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                    "proposals_path": str(proposals_path),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issues = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"]
            coverage_issue = next(issue for issue in issues if issue["code"] == "proposal_coverage_gap")
            self.assertIn("duplicate proposal target cluster", coverage_issue["message"])
            self.assertIn("indexes [0, 1]", coverage_issue["message"])

    def test_run_orchestration_command_reports_duplicate_artifact_target_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "greeting_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                },
                {
                    "name": "farewell_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Bye"]},
                }
            ]), encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": "artifact",
                    "fixture_name": "greeting_test",
                    "confidence": 0.9,
                    "severity": "warning",
                    "content": {
                        "target_path": "references/auto-improver/shared.md",
                        "body": "- Greeting guidance"
                    }
                },
                {
                    "type": "artifact",
                    "fixture_name": "farewell_test",
                    "confidence": 0.92,
                    "severity": "warning",
                    "content": {
                        "target_path": "references/auto-improver/shared.md",
                        "body": "- Farewell guidance"
                    }
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                    "proposals_path": str(proposals_path),
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issues = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"]
            coverage_issue = next(issue for issue in issues if issue["code"] == "proposal_coverage_gap")
            self.assertIn("artifact proposal target_path 'references/auto-improver/shared.md' conflicts", coverage_issue["message"])
            self.assertIn("indexes [0, 1]", coverage_issue["message"])
            self.assertIn("apply order ambiguous", coverage_issue["message"])

    def test_run_orchestration_command_reports_policy_gap_when_all_proposals_will_be_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "greeting_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                }
            ]), encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": "instruction",
                    "fixture_name": "greeting_test",
                    "confidence": 0.7,
                    "severity": "warning"
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                    "proposals_path": str(proposals_path),
                    "min_confidence": 0.9,
                    "accepted_severities": ["critical"]
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issues = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"]
            policy_issue = next(issue for issue in issues if issue["code"] == "proposal_policy_gap")
            self.assertIn("greeting_test", policy_issue["message"])
            self.assertIn("none meet policy", policy_issue["message"])
            self.assertIn("accepted_types=[instruction, test_case]", policy_issue["message"])
            self.assertIn("accepted_severities=[critical]", policy_issue["message"])

    def test_run_orchestration_command_reports_type_policy_gap_when_only_disallowed_types_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "artifact_only_fixture",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                }
            ]), encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": "artifact",
                    "fixture_name": "artifact_only_fixture",
                    "confidence": 0.95,
                    "severity": "critical",
                    "content": {
                        "target_path": "references/auto-improver/artifact-only-fixture.md",
                        "body": "- guidance"
                    }
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                    "proposals_path": str(proposals_path),
                    "accepted_types": ["instruction", "test_case"]
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issues = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"]
            policy_issue = next(issue for issue in issues if issue["code"] == "proposal_policy_gap")
            self.assertIn("artifact_only_fixture", policy_issue["message"])
            self.assertIn("accepted_types=[instruction, test_case]", policy_issue["message"])
            self.assertIn("artifact(confidence=0.95, severity=critical)", policy_issue["message"])

    def test_run_orchestration_command_normalizes_proposal_policy_fields_before_gap_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "shared-brain"
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "greeting_test",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Hello"]},
                }
            ]), encoding="utf-8")
            proposals_path = root / "proposals.json"
            proposals_path.write_text(json.dumps([
                {
                    "type": " Instruction ",
                    "fixture_name": "greeting_test",
                    "confidence": 0.91,
                    "severity": " CRITICAL "
                }
            ]), encoding="utf-8")
            config_path = root / "orchestration.json"
            config_path.write_text(json.dumps([
                {
                    "skill_path": str(skill_dir),
                    "skill_name": "demo_skill",
                    "fixtures_path": str(fixtures_path),
                    "proposals_path": str(proposals_path),
                    "accepted_types": ["instruction", "test_case"],
                    "accepted_severities": ["critical"],
                    "min_confidence": 0.9
                }
            ]), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "run-orchestration",
                    "--brain-dir", str(brain_dir),
                    "--config", str(config_path),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            issues = payload["run"]["skill_outcomes"]["demo_skill"]["preflight_issues"]
            self.assertFalse(any(issue["code"] == "proposal_policy_gap" for issue in issues))

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

    def test_evaluate_golden_command_can_persist_trace_log_and_fail_on_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            fixtures_path = root / "fixtures.json"
            self._write_fixture_file(fixtures_path)
            logs_dir = root / "runs"

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "evaluate-golden",
                    "--skill-path", str(skill_dir),
                    "--fixtures", str(fixtures_path),
                    "--logs-dir", str(logs_dir),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertIn("trace_path", payload)
            trace = json.loads(Path(payload["trace_path"]).read_text(encoding="utf-8"))
            self.assertEqual(trace["metadata"]["cli"]["command"], "evaluate-golden")
            self.assertEqual(trace["steps"][0]["name"], "evaluate")
            self.assertEqual(trace["metadata"]["evaluation"]["mode"], "golden")
            self.assertEqual(trace["metadata"]["evaluation"]["total"], 1)
            self.assertEqual(trace["metadata"]["evaluation"]["failed"], 1)
            self.assertEqual(payload["evaluation"]["passed"], 0)
            self.assertEqual(payload["evaluation"]["failed"], 1)

    def test_evaluate_checklist_command_can_persist_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            checklist_path = root / "checklist.json"
            checklist_path.write_text(json.dumps({
                "name": "quality-gate",
                "questions": [
                    {"id": "has_field_summary", "question": "Has summary?"},
                    {"id": "is_non_empty_title", "question": "Has title?"},
                ],
            }), encoding="utf-8")
            outputs_path = root / "outputs.json"
            outputs_path.write_text(json.dumps({
                "draft": {"summary": "done", "title": "Ship it"}
            }), encoding="utf-8")
            logs_dir = root / "runs"

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "evaluate-checklist",
                    "--skill-path", str(skill_dir),
                    "--checklist", str(checklist_path),
                    "--outputs", str(outputs_path),
                    "--logs-dir", str(logs_dir),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertIn("trace_path", payload)
            trace = json.loads(Path(payload["trace_path"]).read_text(encoding="utf-8"))
            self.assertEqual(trace["metadata"]["cli"]["command"], "evaluate-checklist")
            self.assertEqual(trace["steps"][0]["name"], "evaluate")
            self.assertEqual(trace["metadata"]["evaluation"]["mode"], "checklist")
            self.assertEqual(trace["metadata"]["evaluation"]["total_outputs"], 1)
            self.assertEqual(trace["metadata"]["evaluation"]["total_passed"], 1)

    def test_evaluate_hybrid_command_can_persist_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            fixtures_path = root / "fixtures.json"
            fixtures_path.write_text(json.dumps([
                {
                    "name": "contains_formal",
                    "input_data": {"path": "SKILL.md"},
                    "expected_output": {"contains": ["Use the formal greeting."], "not_contains": []},
                }
            ]), encoding="utf-8")
            checklist_path = root / "checklist.json"
            checklist_path.write_text(json.dumps({
                "name": "quality-gate",
                "questions": [{"id": "has_field_summary", "question": "Has summary?"}],
            }), encoding="utf-8")
            outputs_path = root / "outputs.json"
            outputs_path.write_text(json.dumps({
                "output": {"summary": "ready"}
            }), encoding="utf-8")
            logs_dir = root / "runs"

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "evaluate-hybrid",
                    "--skill-path", str(skill_dir),
                    "--fixtures", str(fixtures_path),
                    "--checklist", str(checklist_path),
                    "--outputs", str(outputs_path),
                    "--logs-dir", str(logs_dir),
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertIn("trace_path", payload)
            trace = json.loads(Path(payload["trace_path"]).read_text(encoding="utf-8"))
            self.assertEqual(trace["metadata"]["cli"]["command"], "evaluate-hybrid")
            self.assertEqual(trace["steps"][0]["name"], "evaluate")
            self.assertEqual(trace["metadata"]["evaluation"]["mode"], "hybrid_either_or")
            self.assertEqual(trace["metadata"]["evaluation"]["fixture_pass_rate"], 0.0)
            self.assertEqual(trace["metadata"]["evaluation"]["checklist_pass_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
