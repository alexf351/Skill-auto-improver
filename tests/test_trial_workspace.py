from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skill_auto_improver.evaluator import GoldenFixture
from skill_auto_improver.trial_workspace import TrialWorkspaceCompiler, render_trial_workspace_markdown


class TrialWorkspaceTests(unittest.TestCase):
    def test_compiler_builds_workspace_with_skill_summary_and_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\n\n# Demo Skill\n", encoding="utf-8")
            (skill_dir / "data").mkdir()
            (skill_dir / "data" / "preferences.json").write_text(
                json.dumps({"proposal": {"min_confidence": 0.9, "prefer_types": ["instruction"]}}),
                encoding="utf-8",
            )

            compiler = TrialWorkspaceCompiler(skill_dir)
            report = compiler.compile(
                fixtures=[GoldenFixture(name="greeting_test", input_data={"path": "SKILL.md"}, expected_output={"contains": ["Demo Skill"]})],
                proposals=[
                    {
                        "fixture_name": "greeting_test",
                        "type": "instruction",
                        "severity": "warning",
                        "confidence": 0.85,
                        "content": {"suggestion": "Use the formal greeting."},
                    }
                ],
                policy={"min_confidence": 0.9, "accepted_severities": ["warning", "critical"]},
            )

            payload = report.to_dict()
            self.assertTrue(payload["skill_summary"]["skill_md_exists"])
            self.assertEqual(payload["fixtures"][0]["probe_mode"], "path")
            self.assertIn("all proposals currently sit below the active confidence floor", payload["warnings"])
            self.assertGreaterEqual(len(payload["warnings"]), 1)
            self.assertGreaterEqual(len(payload["file_map"]), 1)

    def test_compiler_uses_trace_history_to_raise_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            logs_dir = root / "runs"
            logs_dir.mkdir()
            (logs_dir / "trace.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "skill_path": str(skill_dir),
                        "status": "ok",
                        "metadata": {
                            "patch_trial": {
                                "accepted": False,
                                "rolled_back": False,
                                "acceptance_reason": "no proposals applied",
                                "applied_count": 0,
                                "recovered_count": 0,
                                "regressed_count": 0,
                            }
                        },
                        "steps": [],
                    }
                ),
                encoding="utf-8",
            )

            compiler = TrialWorkspaceCompiler(skill_dir, logs_dir=logs_dir)
            report = compiler.compile()
            payload = report.to_dict()
            self.assertIn("recent trials ended with no proposals applied", payload["warnings"])
            self.assertIn("proposal pipeline produced no applied changes recently", payload["trace_summary"]["signals"])

    def test_markdown_renderer_outputs_operator_memo(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            report = TrialWorkspaceCompiler(skill_dir).compile()
            markdown = render_trial_workspace_markdown(report)
            self.assertIn("# Trial Workspace", markdown)
            self.assertIn("## Skill Summary", markdown)
            self.assertIn("## Open Questions", markdown)


if __name__ == "__main__":
    unittest.main()
