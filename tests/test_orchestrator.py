"""
Tests for the multi-skill orchestrator.
"""

import json
import tempfile
import unittest
from pathlib import Path

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
        self.assertTrue(config.enabled)
        self.assertIsNone(config.fixtures_path)

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


if __name__ == "__main__":
    unittest.main()
