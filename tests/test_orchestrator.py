"""
Tests for the multi-skill orchestrator.
"""

import json
import tempfile
import unittest
from pathlib import Path

from skill_auto_improver.loop import SkillAutoImprover
from skill_auto_improver.orchestrator import (
    MultiSkillOrchestrator,
    SkillTrialConfig,
    OrchestrationRun,
)
from skill_auto_improver.shared_brain import SharedBrain


class OrchestratorTests(unittest.TestCase):
    """Test the multi-skill orchestrator."""

    def setUp(self):
        """Create temporary directories for tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name) / "brain"
        self.orchestrator = MultiSkillOrchestrator(brain_dir=self.brain_dir)

    def tearDown(self):
        """Clean up temp directory."""
        self.temp_dir.cleanup()

    def test_orchestrator_creates_shared_brain(self):
        """Orchestrator should initialize shared brain."""
        self.assertIsNotNone(self.orchestrator.shared_brain)
        self.assertTrue(self.orchestrator.brain_dir.exists())

    def test_get_brain_summary(self):
        """Should retrieve summary of shared brain state."""
        summary = self.orchestrator.get_brain_summary()
        
        self.assertIn("core_directives", summary)
        self.assertIn("promotion_wisdom_entries", summary)
        self.assertIn("regression_patterns", summary)
        self.assertIn("fixture_library_entries", summary)
        self.assertIn("skills_tracked", summary)

    def test_orchestration_run_initialization(self):
        """OrchestrationRun should initialize with metadata."""
        run = OrchestrationRun(
            run_id="test_run_001",
            started_at="2026-03-24T00:00:00",
            total_skills=3,
        )
        
        self.assertEqual(run.run_id, "test_run_001")
        self.assertEqual(run.total_skills, 3)
        self.assertIsNone(run.finished_at)

    def test_orchestration_run_to_dict(self):
        """OrchestrationRun should serialize to dict."""
        run = OrchestrationRun(
            run_id="test_run",
            started_at="2026-03-24T00:00:00",
            finished_at="2026-03-24T01:00:00",
            total_skills=2,
            successful_trials=2,
            promotions_accepted=3,
        )
        
        result = run.to_dict()
        
        self.assertEqual(result["run_id"], "test_run")
        self.assertEqual(result["total_skills"], 2)
        self.assertEqual(result["successful_trials"], 2)
        self.assertEqual(result["promotions_accepted"], 3)

    def test_get_skill_context_for_trial(self):
        """Should generate pre-trial context from shared brain."""
        # Set up some directives and mastery
        self.orchestrator.shared_brain.get_or_create_skill_mastery("weather", skill_type="forecast")
        self.orchestrator.shared_brain.update_skill_mastery(
            "weather",
            total_trials=5,
            successful_promotions=3,
        )
        
        context = self.orchestrator.get_skill_context_for_trial("weather")
        
        self.assertIn("applicable_directives", context)
        self.assertIn("regression_patterns_to_watch", context)
        self.assertIn("similar_fixtures_in_library", context)
        self.assertIn("skill_mastery", context)
        
        # Check that mastery is included
        self.assertIsNotNone(context["skill_mastery"])
        self.assertEqual(context["skill_mastery"]["skill_name"], "weather")
        self.assertEqual(context["skill_mastery"]["total_trials"], 5)

    def test_run_empty_orchestration(self):
        """Should handle empty skill configurations."""
        run = self.orchestrator.run_orchestration([])
        
        self.assertIsNotNone(run.run_id)
        self.assertEqual(run.total_skills, 0)
        self.assertIsNotNone(run.finished_at)

    def test_run_orchestration_with_disabled_skills(self):
        """Should skip disabled skills in orchestration."""
        configs = [
            SkillTrialConfig(
                skill_path="/fake/path/a",
                skill_name="skill_a",
                enabled=False,
            ),
            SkillTrialConfig(
                skill_path="/fake/path/b",
                skill_name="skill_b",
                enabled=True,
            ),
        ]
        
        run = self.orchestrator.run_orchestration(configs)
        
        self.assertEqual(run.total_skills, 2)
        # Should attempt skill_b but not skill_a (no errors expected for missing skills)

    def test_orchestration_run_persists_to_logs(self):
        """Should persist orchestration run summary to disk."""
        logs_dir = Path(self.temp_dir.name) / "logs"
        
        run = self.orchestrator.run_orchestration([], logs_dir=logs_dir)
        
        # Check that orchestration log was written
        orchestration_logs = list(logs_dir.glob("orchestration_*.json"))
        self.assertEqual(len(orchestration_logs), 1)
        
        # Verify contents
        data = json.loads(orchestration_logs[0].read_text())
        self.assertEqual(data["run_id"], run.run_id)

    def test_skill_trial_config_basic(self):
        """SkillTrialConfig should store trial parameters."""
        config = SkillTrialConfig(
            skill_path="/path/to/skill",
            skill_name="my_skill",
            skill_type="mobile_app",
            min_confidence=0.85,
        )
        
        self.assertEqual(config.skill_name, "my_skill")
        self.assertEqual(config.skill_type, "mobile_app")
        self.assertEqual(config.min_confidence, 0.85)
        self.assertTrue(config.enabled)

    def test_skill_trial_config_defaults(self):
        """SkillTrialConfig should have sensible defaults."""
        config = SkillTrialConfig(
            skill_path="/path",
            skill_name="test",
        )
        
        self.assertEqual(config.min_confidence, 0.80)
        self.assertEqual(config.accepted_severities, ["warning", "critical"])
        self.assertEqual(config.accepted_types, ["instruction", "test_case"])
        self.assertTrue(config.enabled)
        self.assertIsNone(config.fixtures_path)

    def test_skill_trial_config_normalizes_paths_and_validates_schema(self):
        """SkillTrialConfig should coerce path-like fields and reject invalid schema values."""
        config = SkillTrialConfig(
            skill_path="/path/to/skill",
            skill_name="demo_skill",
            fixtures_path="/path/to/fixtures.json",
            proposals_path="/path/to/proposals.json",
            min_confidence="0.9",
            accepted_severities=[" warning ", "critical"],
            accepted_types=[" instruction ", "artifact"],
        )

        self.assertEqual(config.skill_path, Path("/path/to/skill"))
        self.assertEqual(config.fixtures_path, Path("/path/to/fixtures.json"))
        self.assertEqual(config.proposals_path, Path("/path/to/proposals.json"))
        self.assertEqual(config.min_confidence, 0.9)
        self.assertEqual(config.accepted_severities, ["warning", "critical"])
        self.assertEqual(config.accepted_types, ["instruction", "artifact"])

        with self.assertRaises(ValueError):
            SkillTrialConfig(skill_path="/path", skill_name="demo_skill", accepted_types=[])

        with self.assertRaises(ValueError):
            SkillTrialConfig(skill_path="/path", skill_name="demo_skill", min_confidence=1.2)

        with self.assertRaises(ValueError):
            SkillTrialConfig(skill_path="/path", skill_name="demo_skill", accepted_severities=[])

    def test_orchestrator_brain_updates_on_promotion(self):
        """Orchestrator should record promotions to shared brain."""
        # Simulate recording a promotion through shared brain
        self.orchestrator.shared_brain.record_promotion(
            fixture_name="greeting_test",
            skill_name="weather",
            proposal_types=["test_case", "instruction"],
            reason="100% recovery",
            confidence=0.92,
        )
        
        # Verify it's in the brain
        wisdom = self.orchestrator.shared_brain.get_promotion_wisdom_for_fixture("greeting_test")
        self.assertEqual(len(wisdom), 1)
        self.assertIn("weather", wisdom[0].skills_successful)

    def test_orchestrator_brain_updates_on_regression(self):
        """Orchestrator should record regressions to shared brain."""
        pattern = self.orchestrator.shared_brain.record_regression(
            pattern_name="instruction_only_regression",
            skill_name="kiro",
            trigger="instruction without test_case",
            fix_strategy="require test_case",
        )
        
        # Verify it's in the brain
        patterns = self.orchestrator.shared_brain.get_regression_patterns_for_skill("kiro")
        self.assertGreater(len(patterns), 0)

    def test_multiple_orchestrations_accumulate_brain_state(self):
        """Multiple orchestration runs should accumulate shared brain state."""
        # First orchestration
        self.orchestrator.shared_brain.record_promotion(
            fixture_name="test_1",
            skill_name="skill_a",
            proposal_types=["instruction"],
            reason="good",
            confidence=0.85,
        )
        
        # Second orchestration
        self.orchestrator.shared_brain.record_promotion(
            fixture_name="test_2",
            skill_name="skill_b",
            proposal_types=["test_case"],
            reason="good",
            confidence=0.90,
        )
        
        # Check that both are in brain
        wisdom = self.orchestrator.shared_brain.promotion_wisdom
        self.assertGreaterEqual(len(wisdom), 2)

    def test_orchestrator_can_load_persisted_brain(self):
        """Orchestrator should load brain state persisted from previous run."""
        # First instance: record some state
        orch1 = MultiSkillOrchestrator(brain_dir=self.brain_dir)
        orch1.shared_brain.record_promotion(
            fixture_name="persistent_test",
            skill_name="skill_x",
            proposal_types=["instruction"],
            reason="good",
            confidence=0.88,
        )
        
        # Second instance: should load persisted state
        orch2 = MultiSkillOrchestrator(brain_dir=self.brain_dir)
        wisdom = orch2.shared_brain.get_promotion_wisdom_for_fixture("persistent_test")
        
        self.assertEqual(len(wisdom), 1)
        self.assertIn("skill_x", wisdom[0].skills_successful)

    def test_preflight_trial_config_flags_missing_skill_and_inputs(self):
        """Preflight should catch missing skill, fixtures, and proposals before execution."""
        config = SkillTrialConfig(
            skill_path=Path(self.temp_dir.name) / "missing-skill",
            skill_name="demo_skill",
            fixtures_path=Path(self.temp_dir.name) / "fixtures.json",
            proposals_path=Path(self.temp_dir.name) / "proposals.json",
        )

        issues = self.orchestrator.preflight_trial_config(config)
        codes = {issue.code for issue in issues}

        self.assertIn("missing_skill_path", codes)
        self.assertNotIn("missing_fixtures", codes)  # early return once skill path is missing

    def test_run_orchestration_records_preflight_failure_without_counting_success(self):
        """Invalid configs should create an auditable error trace instead of false success metrics."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n", encoding="utf-8")

            config = SkillTrialConfig(
                skill_path=skill_dir,
                skill_name="demo_skill",
                fixtures_path=root / "missing-fixtures.json",
            )

            run = self.orchestrator.run_orchestration([config])

            self.assertEqual(run.successful_trials, 0)
            self.assertEqual(run.rolled_back_trials, 0)
            outcome = run.skill_outcomes["demo_skill"]
            self.assertEqual(outcome["status"], "error")
            self.assertFalse(outcome["preflight_ok"])
            self.assertEqual(outcome["preflight_issues"][0]["code"], "missing_fixtures")
            trace = run.skill_trials["demo_skill"]
            self.assertEqual(trace.steps[0].name, "preflight")

    def test_preflight_trial_config_validates_fixture_probe_shape(self):
        """Preflight should catch malformed fixture probes before evaluate-time failures."""
        skill_dir = Path(self.temp_dir.name) / "fixture-shape-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-invalid.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "bad_fixture",
                "input_data": {"command": "python3 check.py", "path": "SKILL.md"},
                "expected_output": {"contains": ["Hello"]},
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertEqual(issues[0].code, "invalid_fixtures_shape")
        self.assertIn("exactly one of input_data.path or input_data.command", issues[0].message)

    def test_preflight_trial_config_rejects_command_probe_cwd_outside_skill_root(self):
        """Preflight should fail command fixtures that try to execute outside the target skill."""
        skill_dir = Path(self.temp_dir.name) / "fixture-cwd-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-cwd-invalid.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "bad_cwd_fixture",
                "input_data": {"command": ["python3", "check.py"], "cwd": "../outside"},
                "expected_output": {"stdout_contains": ["Hello"]},
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertEqual(issues[0].code, "invalid_fixtures_shape")
        self.assertIn("input_data.cwd must stay inside the skill root", issues[0].message)

    def test_preflight_trial_config_validates_proposal_semantics(self):
        """Preflight should catch proposal confidence/fixture metadata issues early."""
        skill_dir = Path(self.temp_dir.name) / "proposal-shape-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-invalid.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "instruction",
                "fixture_name": "",
                "confidence": 1.5,
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            proposals_path=proposals_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertEqual(issues[0].code, "invalid_proposals_shape")
        self.assertIn("fixture_name", issues[0].message)
        self.assertIn("between 0.0 and 1.0", issues[0].message)

    def test_preflight_trial_config_validates_proposal_fixture_links(self):
        """Preflight should catch proposals that target fixtures not present in the fixtures file."""
        skill_dir = Path(self.temp_dir.name) / "proposal-link-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-valid.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "greeting_test",
                "input_data": {"path": "SKILL.md"},
                "expected_output": {"contains": ["Hello"]},
            }
        ]), encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-link-invalid.json"
        proposals_path.write_text(json.dumps({
            "proposals": [
                {
                    "type": "instruction",
                    "fixture_name": "missing_fixture",
                    "confidence": 0.9,
                    "severity": "warning",
                }
            ]
        }), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertEqual(issues[-1].code, "proposal_coverage_gap")
        self.assertIn("greeting_test", issues[-1].message)
        self.assertIn("fixtures without matching proposals", issues[-1].message)

    def test_preflight_trial_config_rejects_duplicate_fixture_names(self):
        """Preflight should fail duplicate fixture names because proposal targeting becomes ambiguous."""
        skill_dir = Path(self.temp_dir.name) / "duplicate-fixture-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-duplicate.json"
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

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertEqual(issues[0].code, "invalid_fixtures_shape")
        self.assertIn("duplicates index 0", issues[0].message)
        self.assertIn("proposal targeting ambiguous", issues[0].message)

    def test_preflight_trial_config_reports_fixture_coverage_gaps(self):
        """Preflight should surface fixtures that have no matching proposal in unattended runs."""
        skill_dir = Path(self.temp_dir.name) / "coverage-gap-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-coverage.json"
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
        proposals_path = Path(self.temp_dir.name) / "proposals-coverage.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "instruction",
                "fixture_name": "greeting_test",
                "confidence": 0.9,
                "severity": "warning",
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        coverage_issue = next(issue for issue in issues if issue.code == "proposal_coverage_gap")
        self.assertIn("fixtures without matching proposals", coverage_issue.message)
        self.assertIn("farewell_test", coverage_issue.message)

    def test_preflight_trial_config_rejects_duplicate_proposal_targets(self):
        """Preflight should fail duplicate proposal fixture/type targets because apply order becomes ambiguous."""
        skill_dir = Path(self.temp_dir.name) / "duplicate-proposals-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-proposals.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "greeting_test",
                "input_data": {"path": "SKILL.md"},
                "expected_output": {"contains": ["Hello"]},
            }
        ]), encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-duplicate.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "instruction",
                "fixture_name": "greeting_test",
                "confidence": 0.9,
                "severity": "warning",
            },
            {
                "type": "instruction",
                "fixture_name": "greeting_test",
                "confidence": 0.95,
                "severity": "critical",
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        coverage_issue = next(issue for issue in issues if issue.code == "proposal_coverage_gap")
        self.assertIn("duplicate proposal target cluster", coverage_issue.message)
        self.assertIn("indexes [0, 1]", coverage_issue.message)

    def test_preflight_trial_config_rejects_artifact_targets_outside_skill_root(self):
        """Preflight should fail artifact proposals that attempt to escape the skill directory."""
        skill_dir = Path(self.temp_dir.name) / "artifact-safety-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-artifact-invalid.json"
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

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            proposals_path=proposals_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertEqual(issues[0].code, "invalid_proposals_shape")
        self.assertIn("escapes the skill root", issues[0].message)

    def test_preflight_trial_config_rejects_duplicate_artifact_target_paths(self):
        """Preflight should fail artifact proposals that target the same file because apply order becomes ambiguous."""
        skill_dir = Path(self.temp_dir.name) / "artifact-conflict-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-artifact-conflict.json"
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
        proposals_path = Path(self.temp_dir.name) / "proposals-artifact-conflict.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "artifact",
                "fixture_name": "greeting_test",
                "confidence": 0.9,
                "severity": "warning",
                "content": {
                    "target_path": "references/auto-improver/shared.md",
                    "body": "- Greeting guidance",
                },
            },
            {
                "type": "artifact",
                "fixture_name": "farewell_test",
                "confidence": 0.92,
                "severity": "warning",
                "content": {
                    "target_path": "references/auto-improver/shared.md",
                    "body": "- Farewell guidance",
                },
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        coverage_issue = next(issue for issue in issues if issue.code == "proposal_coverage_gap")
        self.assertIn("artifact proposal target_path 'references/auto-improver/shared.md' conflicts", coverage_issue.message)
        self.assertIn("indexes [0, 1]", coverage_issue.message)
        self.assertIn("apply order ambiguous", coverage_issue.message)

    def test_preflight_trial_config_flags_fixtures_with_only_policy_blocked_proposals(self):
        """Preflight should surface unattended runs where proposals exist but policy guarantees they will be skipped."""
        skill_dir = Path(self.temp_dir.name) / "policy-gap-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-policy-gap.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "greeting_test",
                "input_data": {"path": "SKILL.md"},
                "expected_output": {"contains": ["Hello"]},
            }
        ]), encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-policy-gap.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "instruction",
                "fixture_name": "greeting_test",
                "confidence": 0.7,
                "severity": "warning",
            },
            {
                "type": "test_case",
                "fixture_name": "greeting_test",
                "confidence": 0.75,
                "severity": "info",
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
            min_confidence=0.9,
            accepted_severities=["critical"],
        )

        issues = self.orchestrator.preflight_trial_config(config)
        policy_issue = next(issue for issue in issues if issue.code == "proposal_policy_gap")
        self.assertIn("greeting_test", policy_issue.message)
        self.assertIn("none meet policy", policy_issue.message)
        self.assertIn("accepted_types=[instruction, test_case]", policy_issue.message)
        self.assertIn("min_confidence=0.90", policy_issue.message)
        self.assertIn("accepted_severities=[critical]", policy_issue.message)

    def test_get_skill_context_includes_applicable_directives(self):
        """Skill context should include directives applicable to that skill."""
        context = self.orchestrator.get_skill_context_for_trial("weather_brief")
        
        # Should include at least the wildcard directives
        self.assertGreater(len(context["applicable_directives"]), 0)
        
        # All directives should be applicable to this skill
        for directive in context["applicable_directives"]:
            self.assertTrue(
                any(p == "*" or p in "weather_brief" for p in directive.get("applies_to", []))
            )

    def test_run_skill_trial_persists_orchestration_context_metadata(self):
        """Per-skill orchestration config + brain context should be auditable in the trace."""
        skill_dir = Path(self.temp_dir.name) / "demo-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures.json"
        fixtures_path.write_text(json.dumps([
            {"name": "greeting_formal_check", "input_data": {"path": "SKILL.md"}, "expected_output": {"contains": ["Hello"]}}
        ]), encoding="utf-8")
        self.orchestrator.shared_brain.add_fixture_to_library(
            fixture_pattern_name="greeting_formal",
            fixture_template={"name": "greeting_formal"},
            expected_behavior="Formal greeting stays present",
            successful_skills=["weather"],
        )

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            min_confidence=0.91,
            accepted_severities=["critical"],
        )

        trace = self.orchestrator._run_skill_trial(config, OrchestrationRun(run_id="r1", started_at="2026-03-27T00:00:00+00:00"))
        self.assertIsNotNone(trace)
        orchestration_meta = trace.metadata["orchestration"]
        self.assertEqual(orchestration_meta["config"]["min_confidence"], 0.91)
        self.assertEqual(orchestration_meta["config"]["accepted_severities"], ["critical"])
        self.assertEqual(orchestration_meta["config"]["accepted_types"], ["instruction", "test_case"])
        self.assertEqual(orchestration_meta["fixture_names"], ["greeting_formal_check"])
        self.assertEqual(orchestration_meta["fixture_suggestions"]["greeting_formal_check"][0]["pattern_name"], "greeting_formal")

    def test_create_improver_factory_can_receive_config_and_brain_context(self):
        """Orchestrator should pass rich trial context into newer improver factories."""
        skill_dir = Path(self.temp_dir.name) / "config-aware-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        captured: dict[str, object] = {}

        def factory(skill_path: Path, config: SkillTrialConfig, brain_context: dict[str, object]) -> SkillAutoImprover:
            captured["skill_path"] = skill_path
            captured["config"] = config
            captured["brain_context"] = brain_context
            return SkillAutoImprover(
                observe=lambda ctx: {"ok": True},
                inspect=lambda ctx: {"config_min_confidence": config.min_confidence},
                amend=lambda ctx: {},
                evaluate=lambda ctx: {"status": "ok"},
            )

        orchestrator = MultiSkillOrchestrator(brain_dir=self.brain_dir, create_improver=factory)
        config = SkillTrialConfig(skill_path=skill_dir, skill_name="demo_skill", min_confidence=0.93)
        trace = orchestrator._run_skill_trial(config, OrchestrationRun(run_id="r2", started_at="2026-03-27T00:00:00+00:00"))

        self.assertIsNotNone(trace)
        self.assertEqual(captured["skill_path"], skill_dir)
        self.assertEqual(captured["config"].skill_name, "demo_skill")
        self.assertEqual(captured["brain_context"]["config"]["min_confidence"], 0.93)
        self.assertEqual(captured["brain_context"]["config"]["accepted_types"], ["instruction", "test_case"])
        inspect_step = next(step for step in trace.steps if step.name == "inspect")
        self.assertEqual(inspect_step.output["config_min_confidence"], 0.93)

    def test_extract_and_record_insights_uses_per_trial_counts_not_run_totals(self):
        """Outcome summaries should reflect this trial, not cumulative orchestration counters."""
        run = OrchestrationRun(run_id="r3", started_at="2026-03-27T00:00:00+00:00")
        config = SkillTrialConfig(skill_path="/tmp/demo", skill_name="demo_skill", min_confidence=0.88)
        trace = SkillAutoImprover(
            observe=lambda ctx: {},
            inspect=lambda ctx: {},
            amend=lambda ctx: {},
            evaluate=lambda ctx: {},
        ).run_once(skill_path="/tmp/demo", logs_dir=Path(self.temp_dir.name) / "runs")
        trace.metadata["patch_trial"] = {
            "accepted": True,
            "rolled_back": False,
            "acceptance_reason": "safe improvement",
            "apply": {
                "applied_count": 1,
                "skipped_count": 1,
                "applied": [{"proposal_type": "test_case"}],
                "skipped": [{"proposal_type": "instruction"}],
            },
            "ab": {"pass_rate_delta": 0.5, "recovered_count": 2, "regressed_count": 0, "is_safe": True},
        }

        self.orchestrator._extract_and_record_insights(config, trace, run)

        outcome = run.skill_outcomes["demo_skill"]
        self.assertEqual(outcome["promotions_from_trial"], 2)
        self.assertEqual(outcome["regressions_from_trial"], 0)
        self.assertEqual(outcome["proposal_types"], ["instruction", "test_case"])
        mastery = self.orchestrator.shared_brain.get_skill_mastery("demo_skill")
        self.assertEqual(mastery.average_proposal_confidence, 0.88)

    def test_extract_and_record_insights_accepts_flat_patch_trial_metadata_from_loop(self):
        """Flat trace metadata from loop._update_trace_metadata should still feed orchestrator insights."""
        run = OrchestrationRun(run_id="r4", started_at="2026-03-28T00:00:00+00:00")
        config = SkillTrialConfig(skill_path="/tmp/demo", skill_name="demo_skill", min_confidence=0.9)
        trace = SkillAutoImprover(
            observe=lambda ctx: {},
            inspect=lambda ctx: {},
            amend=lambda ctx: {},
            evaluate=lambda ctx: {},
        ).run_once(skill_path="/tmp/demo", logs_dir=Path(self.temp_dir.name) / "runs")
        trace.metadata["patch_trial"] = {
            "accepted": True,
            "rolled_back": False,
            "acceptance_reason": "safe improvement",
            "applied_count": 1,
            "skipped_count": 1,
            "recovered_count": 3,
            "regressed_count": 0,
            "pass_rate_delta": 0.75,
            "is_safe": True,
            "diff_summaries": [],
            "backup_ids": [],
            "promotion_guard": None,
            "promotion": None,
            "operating_memory": None,
            "backup_summary": {"total_backups": 1},
            "applied": [{"proposal_type": "test_case"}],
            "skipped": [{"proposal_type": "instruction"}],
        }

        self.orchestrator._extract_and_record_insights(config, trace, run)

        outcome = run.skill_outcomes["demo_skill"]
        self.assertEqual(outcome["promotions_from_trial"], 3)
        self.assertEqual(outcome["proposal_types"], ["instruction", "test_case"])
        self.assertEqual(run.promotions_accepted, 1)

    def test_preflight_trial_config_flags_type_only_policy_gaps(self):
        """Preflight should surface unattended runs where proposal types are guaranteed to be skipped."""
        skill_dir = Path(self.temp_dir.name) / "type-gap-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-type-gap.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "artifact_only_fixture",
                "input_data": {"path": "SKILL.md"},
                "expected_output": {"contains": ["Hello"]},
            }
        ]), encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-type-gap.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "artifact",
                "fixture_name": "artifact_only_fixture",
                "confidence": 0.95,
                "severity": "critical",
                "content": {
                    "target_path": "references/auto-improver/artifact-only-fixture.md",
                    "body": "- guidance",
                },
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
            accepted_types=["instruction", "test_case"],
        )

        issues = self.orchestrator.preflight_trial_config(config)
        policy_issue = next(issue for issue in issues if issue.code == "proposal_policy_gap")
        self.assertIn("artifact_only_fixture", policy_issue.message)
        self.assertIn("accepted_types=[instruction, test_case]", policy_issue.message)
        self.assertIn("artifact(confidence=0.95, severity=critical)", policy_issue.message)

    def test_preflight_trial_config_clusters_multi_way_duplicate_conflicts(self):
        """Preflight should report one clustered issue when 3+ proposals collide on the same target."""
        skill_dir = Path(self.temp_dir.name) / "clustered-conflict-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-clustered-conflict.json"
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
            },
            {
                "name": "tone_test",
                "input_data": {"path": "SKILL.md"},
                "expected_output": {"contains": ["Formal"]},
            }
        ]), encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-clustered-conflict.json"
        proposals_path.write_text(json.dumps([
            {
                "type": "artifact",
                "fixture_name": "greeting_test",
                "confidence": 0.9,
                "severity": "warning",
                "content": {"target_path": "references/auto-improver/shared.md", "body": "- Greeting guidance"},
            },
            {
                "type": "artifact",
                "fixture_name": "farewell_test",
                "confidence": 0.92,
                "severity": "warning",
                "content": {"target_path": "references/auto-improver/shared.md", "body": "- Farewell guidance"},
            },
            {
                "type": "artifact",
                "fixture_name": "tone_test",
                "confidence": 0.93,
                "severity": "critical",
                "content": {"target_path": "references/auto-improver/shared.md", "body": "- Tone guidance"},
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
            accepted_types=["artifact"],
        )

        issues = self.orchestrator.preflight_trial_config(config)
        coverage_issue = next(issue for issue in issues if issue.code == "proposal_coverage_gap")
        self.assertEqual(coverage_issue.message.count("references/auto-improver/shared.md"), 1)
        self.assertIn("indexes [0, 1, 2]", coverage_issue.message)

    def test_preflight_trial_config_normalizes_proposal_policy_fields_before_gap_detection(self):
        """Preflight should treat proposal type/severity case and whitespace consistently with operator policy."""
        skill_dir = Path(self.temp_dir.name) / "normalized-policy-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
        fixtures_path = Path(self.temp_dir.name) / "fixtures-normalized-policy.json"
        fixtures_path.write_text(json.dumps([
            {
                "name": "greeting_test",
                "input_data": {"path": "SKILL.md"},
                "expected_output": {"contains": ["Hello"]},
            }
        ]), encoding="utf-8")
        proposals_path = Path(self.temp_dir.name) / "proposals-normalized-policy.json"
        proposals_path.write_text(json.dumps([
            {
                "type": " Instruction ",
                "fixture_name": "greeting_test",
                "confidence": 0.91,
                "severity": " CRITICAL ",
            }
        ]), encoding="utf-8")

        config = SkillTrialConfig(
            skill_path=skill_dir,
            skill_name="demo_skill",
            fixtures_path=fixtures_path,
            proposals_path=proposals_path,
            accepted_types=["instruction", "test_case"],
            accepted_severities=["critical"],
            min_confidence=0.9,
        )

        issues = self.orchestrator.preflight_trial_config(config)
        self.assertFalse(any(issue.code == "proposal_policy_gap" for issue in issues))

    def test_run_skill_trial_rewrites_persisted_trace_with_orchestration_metadata(self):
        """Enriched orchestration metadata should be persisted, not only available in-memory."""
        skill_dir = Path(self.temp_dir.name) / "persisted-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")

        config = SkillTrialConfig(skill_path=skill_dir, skill_name="persisted_skill")
        trace = self.orchestrator._run_skill_trial(config, OrchestrationRun(run_id="r5", started_at="2026-03-28T00:00:00+00:00"))

        self.assertIsNotNone(trace)
        trace_path = self.brain_dir.parent / "runs" / f"{trace.run_id}.json"
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        self.assertIn("orchestration", payload["metadata"])
        self.assertIn("patch_trial", payload["metadata"])
        self.assertTrue(any(step["name"] == "patch_trial" for step in payload["steps"]))


if __name__ == "__main__":
    unittest.main()
