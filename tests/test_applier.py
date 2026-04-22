from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.applier import SkillPatchApplier
from skill_auto_improver.proposer import PatchProposal


class SkillPatchApplierTests(unittest.TestCase):
    def _instruction_proposal(self) -> PatchProposal:
        return PatchProposal(
            type="instruction",
            description="Tighten instructions for greeting_test",
            content={
                "suggestion": "Tell the model to use the formal greeting.",
                "mismatched_fields": ["greeting"],
            },
            fixture_name="greeting_test",
            severity="warning",
            confidence=0.85,
        )

    def _test_case_proposal(self) -> PatchProposal:
        return PatchProposal(
            type="test_case",
            description="Add regression test for greeting_test",
            content={
                "fixture": {
                    "name": "greeting_test_regression",
                    "input_data": {"name": "Alice"},
                    "expected_output": {"greeting": "Hello, Alice!"},
                    "tags": ["regression"],
                }
            },
            fixture_name="greeting_test",
            severity="info",
            confidence=0.9,
        )

    def _artifact_proposal(self) -> PatchProposal:
        return PatchProposal(
            type="artifact",
            description="Document safeguard for greeting_test",
            content={
                "target_path": "references/auto-improver/greeting_test.md",
                "section_title": "Greeting safeguard",
                "body": "- Keep greetings formal\n- Re-check promoted behavior before edits",
            },
            fixture_name="greeting_test",
            severity="warning",
            confidence=0.91,
        )

    def test_apply_instruction_appends_note_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._instruction_proposal()])

            self.assertEqual(report.applied_count, 1)
            updated = skill_md.read_text(encoding="utf-8")
            self.assertIn("Auto-Improver Proposed Instruction Update", updated)
            backups = list((skill_dir / ".skill-auto-improver" / "backups").glob("SKILL.md.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertIsNotNone(report.applied[0].backup_id)
            self.assertGreater(report.applied[0].diff_summary["added_lines"], 0)
            self.assertTrue(any("Auto-Improver Proposed Instruction Update" in line for line in report.applied[0].diff_summary["preview"]))

    def test_apply_test_case_creates_golden_fixtures_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._test_case_proposal()])

            self.assertEqual(report.applied_count, 1)
            fixtures = json.loads((skill_dir / "golden-fixtures.json").read_text(encoding="utf-8"))
            self.assertEqual(fixtures[0]["name"], "greeting_test_regression")
            self.assertEqual(report.applied[0].backup_id, None)
            self.assertGreater(report.applied[0].diff_summary["added_lines"], 0)
            self.assertTrue(any("greeting_test_regression" in line for line in report.applied[0].diff_summary["preview"]))

    def test_apply_artifact_creates_supporting_reference_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._artifact_proposal()])

            self.assertEqual(report.applied_count, 1)
            artifact_path = skill_dir / "references" / "auto-improver" / "greeting_test.md"
            self.assertTrue(artifact_path.exists())
            self.assertIn("Greeting safeguard", artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(report.applied[0].proposal_type, "artifact")

    def test_apply_artifact_preserves_checklist_style_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            proposal = PatchProposal(
                type="artifact",
                description="Checklist safeguard for greeting_test",
                content={
                    "target_path": "checklists/auto-improver/greeting_test.md",
                    "format": "markdown_checklist",
                    "section_title": "Greeting checklist",
                    "body": "- [ ] Keep greetings formal\n- [ ] Re-run fixture",
                },
                fixture_name="greeting_test",
                severity="warning",
                confidence=0.92,
            )

            report = SkillPatchApplier(skill_dir).apply([proposal])
            artifact_path = skill_dir / "checklists" / "auto-improver" / "greeting_test.md"
            self.assertEqual(report.applied_count, 1)
            self.assertTrue(artifact_path.exists())
            content = artifact_path.read_text(encoding="utf-8")
            self.assertIn("Greeting checklist", content)
            self.assertIn("- [ ] Keep greetings formal", content)

    def test_apply_instruction_updates_existing_fixture_block_instead_of_appending_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                "# Demo Skill\n\n## Auto-Improver Proposed Instruction Update\n- Fixture: greeting_test\n- Severity: warning\n- Mismatched fields: greeting\n- Suggestion: Old wording\n",
                encoding="utf-8",
            )

            report = SkillPatchApplier(skill_dir).apply([self._instruction_proposal()])
            updated = skill_md.read_text(encoding="utf-8")
            self.assertEqual(report.applied_count, 1)
            self.assertEqual(updated.count("## Auto-Improver Proposed Instruction Update"), 1)
            self.assertIn("Tell the model to use the formal greeting.", updated)
            self.assertIn("updated", report.applied[0].detail)

    def test_apply_artifact_updates_existing_fixture_file_instead_of_appending_duplicate_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            artifact_path = skill_dir / "references" / "auto-improver" / "greeting_test.md"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text(
                "# Greeting safeguard\n\n- Old safeguard\n",
                encoding="utf-8",
            )

            report = SkillPatchApplier(skill_dir).apply([self._artifact_proposal()])
            updated = artifact_path.read_text(encoding="utf-8")
            self.assertEqual(report.applied_count, 1)
            self.assertEqual(updated.count("# Greeting safeguard"), 1)
            self.assertIn("Keep greetings formal", updated)
            self.assertIn("updated", report.applied[0].detail)

    def test_dry_run_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._instruction_proposal(), self._test_case_proposal()], mode="plan")

            self.assertEqual(report.applied_count, 2)
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "# Demo Skill\n")
            self.assertFalse((skill_dir / "golden-fixtures.json").exists())

    def test_duplicate_fixture_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            fixtures_path = skill_dir / "golden-fixtures.json"
            fixtures_path.write_text(json.dumps([{"name": "greeting_test_regression", "input_data": {"name": "Alice"}, "expected_output": {"greeting": "Hello, Alice!"}}]), encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._test_case_proposal()])

            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertIn("already exists", report.skipped[0].detail)

    def test_inspect_backups_can_link_trial_history_by_backup_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._instruction_proposal()])

            inspections = applier.inspect_backups(
                history_entries=[
                    {
                        "timestamp": "2026-04-08T11:00:00+00:00",
                        "accepted": True,
                        "rolled_back": False,
                        "acceptance_reason": "recovered fixtures without regressions",
                        "fixture_names": ["greeting_test"],
                        "backup_refs": [
                            {
                                "backup_id": report.applied[0].backup_id,
                                "target_path": report.applied[0].target_path,
                                "proposal_type": report.applied[0].proposal_type,
                                "fixture_name": report.applied[0].fixture_name,
                            }
                        ],
                    }
                ],
            )

            self.assertEqual(len(inspections), 1)
            self.assertEqual(len(inspections[0].trial_refs), 1)
            self.assertEqual(inspections[0].trial_refs[0]["acceptance_reason"], "recovered fixtures without regressions")
            self.assertEqual(inspections[0].trial_refs[0]["backup_ref"]["backup_id"], report.applied[0].backup_id)

    def test_reasoning_proposals_are_skipped_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            proposal = PatchProposal(type="reasoning", description="Diagnostic only", content={"note": "no-op"}, fixture_name="greeting_test")
            report = SkillPatchApplier(skill_dir).apply([proposal])

            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertEqual(report.skipped[0].detail, "proposal type not accepted")

    def test_low_confidence_proposals_can_be_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            report = SkillPatchApplier(skill_dir).apply([self._instruction_proposal()], min_confidence=0.9)
            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertIn("below minimum", report.skipped[0].detail)

    def test_severity_allowlist_can_block_proposals(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            report = SkillPatchApplier(skill_dir).apply([self._instruction_proposal()], accepted_severities={"info"})
            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertIn("severity 'warning' not accepted", report.skipped[0].detail)

    def test_fixture_policy_can_require_companion_test_case_before_auto_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            report = SkillPatchApplier(skill_dir).apply(
                [self._instruction_proposal()],
                fixture_policies={"greeting_test": {"required_proposal_types": ["test_case"]}},
            )
            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertIn("requires proposal types", report.skipped[0].detail)

    def test_fixture_policy_can_raise_min_confidence_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            report = SkillPatchApplier(skill_dir).apply(
                [self._instruction_proposal()],
                fixture_policies={"greeting_test": {"min_confidence": 0.9}},
            )
            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertIn("below minimum 0.90", report.skipped[0].detail)

    def test_fixture_policy_can_override_global_severity_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            report = SkillPatchApplier(skill_dir).apply(
                [self._instruction_proposal()],
                accepted_severities={"warning", "critical"},
                fixture_policies={"greeting_test": {"accepted_severities": ["critical"]}},
            )
            self.assertEqual(report.applied_count, 0)
            self.assertEqual(report.skipped_count, 1)
            self.assertIn("for fixture 'greeting_test'", report.skipped[0].detail)

    def test_list_backups_returns_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            applier.apply([self._instruction_proposal()])
            skill_md.write_text("# Demo Skill\n\nsecond version\n", encoding="utf-8")
            applier.apply([self._instruction_proposal()])

            backups = applier.list_backups()
            self.assertEqual(len(backups), 2)
            self.assertTrue(backups[0].backup_path.endswith(".bak"))
            self.assertGreaterEqual(backups[0].created_at, backups[1].created_at)
            self.assertTrue(backups[0].target_path.endswith("SKILL.md"))

    def test_inspect_backups_includes_current_diff_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            applier.apply([self._instruction_proposal()])
            backup = applier.list_backups()[0]

            skill_md.write_text("# Demo Skill\n\nBROKEN\n", encoding="utf-8")
            inspections = applier.inspect_backups(target_name="SKILL.md")

            self.assertEqual(len(inspections), 1)
            self.assertEqual(inspections[0].backup_path, backup.backup_path)
            self.assertTrue(inspections[0].current_exists)
            self.assertIsNotNone(inspections[0].current_diff)
            self.assertGreater(inspections[0].current_diff["added_lines"], 0)
            self.assertTrue(any("BROKEN" in line for line in inspections[0].current_diff["preview"]))

    def test_restore_backup_restores_previous_file_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            applier.apply([self._instruction_proposal()])
            backup = applier.list_backups()[0]

            skill_md.write_text("# Demo Skill\n\nBROKEN\n", encoding="utf-8")
            report = applier.restore_backup(backup.backup_path)

            self.assertTrue(report.restored)
            self.assertTrue(report.checksum_verified)
            self.assertIsNotNone(report.pre_restore_backup_path)
            self.assertTrue(Path(report.pre_restore_backup_path).exists())
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "# Demo Skill\n")

    def test_resolve_backup_can_find_entry_by_backup_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            applier = SkillPatchApplier(skill_dir)
            applier.apply([self._instruction_proposal()])
            backup = applier.list_backups()[0]

            resolved = applier.resolve_backup(backup.created_at, target_name="SKILL.md")
            self.assertIsNotNone(resolved)
            self.assertEqual(Path(resolved), Path(backup.backup_path))

    def test_restore_backup_missing_file_returns_failure_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            applier = SkillPatchApplier(skill_dir)
            report = applier.restore_backup(skill_dir / ".skill-auto-improver" / "backups" / "missing.bak")
            self.assertFalse(report.restored)
            self.assertEqual(report.detail, "backup not found")

    def test_restore_backup_rejects_tampered_backup_when_checksum_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            applier.apply([self._instruction_proposal()])
            backup = Path(applier.list_backups()[0].backup_path)
            backup.write_text("tampered\n", encoding="utf-8")

            skill_md.write_text("# Demo Skill\n\nBROKEN\n", encoding="utf-8")
            report = applier.restore_backup(backup)

            self.assertFalse(report.restored)
            self.assertFalse(report.checksum_verified)
            self.assertEqual(report.detail, "backup checksum verification failed")
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "# Demo Skill\n\nBROKEN\n")

    def test_restore_latest_backup_restores_newest_matching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            applier.apply([self._instruction_proposal()])
            skill_md.write_text("# Demo Skill\n\nsecond version\n", encoding="utf-8")
            applier.apply([self._instruction_proposal()])

            skill_md.write_text("BROKEN\n", encoding="utf-8")
            report = applier.restore_latest_backup(target_name="SKILL.md")

            self.assertTrue(report.restored)
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "# Demo Skill\n\nsecond version\n")

    def test_restore_latest_backup_returns_failure_when_target_has_no_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.restore_latest_backup(target_name="golden-fixtures.json")

            self.assertFalse(report.restored)
            self.assertIn("no backups found", report.detail)
            self.assertTrue(report.target_path.endswith("golden-fixtures.json"))


    def test_inspect_backups_shows_checksum_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# Demo Skill\n", encoding="utf-8")

            applier = SkillPatchApplier(skill_dir)
            report = applier.apply([self._instruction_proposal()])
            backup_path = Path(report.applied[0].backup_path)

            # Valid backup
            inspections = applier.inspect_backups(limit=1)
            self.assertEqual(len(inspections), 1)
            self.assertTrue(inspections[0].checksum_verified)

            # Tamper backup
            backup_path.write_text("tampered\n", encoding="utf-8")
            inspections = applier.inspect_backups(limit=1)
            self.assertFalse(inspections[0].checksum_verified)

            # Missing checksum file (simulate by removing)
            checksum_path = applier._backup_checksum_path(backup_path)
            checksum_path.unlink()
            inspections = applier.inspect_backups(limit=1)
            self.assertFalse(inspections[0].checksum_verified)


if __name__ == "__main__":
    unittest.main()
