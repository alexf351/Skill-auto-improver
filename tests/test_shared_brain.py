"""
Tests for the shared brain multi-skill orchestration layer.
"""

import json
import tempfile
import unittest
from pathlib import Path

from skill_auto_improver.shared_brain import (
    SharedBrain,
    CoreDirective,
    PromotionWisdom,
    RegressionPattern,
    FixtureLibraryEntry,
    SkillMastery,
)


class SharedBrainTests(unittest.TestCase):
    """Test the shared brain memory system."""

    def setUp(self):
        """Create a temporary brain directory for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name)
        self.brain = SharedBrain(self.brain_dir)

    def tearDown(self):
        """Clean up temp directory."""
        self.temp_dir.cleanup()

    def test_shared_brain_init_creates_directories(self):
        """Brain should create directory structure on init."""
        self.assertTrue(self.brain_dir.exists())

    def test_shared_brain_loads_default_directives(self):
        """Brain should load default core directives on init."""
        directives = self.brain.core_directives
        self.assertGreater(len(directives), 0)
        self.assertIn("cd_001_min_confidence", directives)

    def test_core_directive_matches_skill_by_exact_pattern(self):
        """Directive should match skill by exact wildcard pattern."""
        directive = CoreDirective(
            id="cd_test",
            title="Test",
            description="Test directive",
            applies_to=["weather*"],
            auto_apply=True,
        )
        
        self.assertTrue(directive.matches_skill("weather-brief"))
        self.assertTrue(directive.matches_skill("weather_research"))
        self.assertFalse(directive.matches_skill("kiro-app"))

    def test_core_directive_matches_all_with_wildcard(self):
        """Directive with ['*'] should match any skill."""
        directive = self.brain.core_directives["cd_001_min_confidence"]
        
        self.assertTrue(directive.matches_skill("kiro"))
        self.assertTrue(directive.matches_skill("weather"))
        self.assertTrue(directive.matches_skill("any_skill"))

    def test_get_directives_for_skill(self):
        """Should retrieve directives applicable to a skill."""
        directives = self.brain.get_directives_for_skill("kiro")
        self.assertGreater(len(directives), 0)

    def test_record_promotion(self):
        """Should record promotion wisdom for cross-skill learning."""
        wisdom = self.brain.record_promotion(
            fixture_name="formal_greeting_test",
            skill_name="weather-brief",
            proposal_types=["test_case", "instruction"],
            reason="100% recovery, zero regressions",
            confidence=0.92,
            shared_lessons=["Always pair instruction with test_case for greeting tests"],
        )
        
        self.assertIsNotNone(wisdom)
        self.assertEqual(wisdom.fixture_name, "formal_greeting_test")
        self.assertIn("weather-brief", wisdom.skills_successful)
        self.assertEqual(wisdom.confidence, 0.92)

    def test_record_promotion_merges_with_existing(self):
        """Recording same fixture in different skill should merge wisdom entries."""
        wisdom1 = self.brain.record_promotion(
            fixture_name="greeting_test",
            skill_name="skill_a",
            proposal_types=["test_case"],
            reason="Good recovery",
            confidence=0.90,
        )
        
        wisdom2 = self.brain.record_promotion(
            fixture_name="greeting_test",
            skill_name="skill_b",
            proposal_types=["test_case"],
            reason="Good recovery",
            confidence=0.88,
        )
        
        # Should be same wisdom ID (merged)
        self.assertEqual(wisdom1.id, wisdom2.id)
        self.assertEqual(len(wisdom2.skills_successful), 2)
        self.assertIn("skill_a", wisdom2.skills_successful)
        self.assertIn("skill_b", wisdom2.skills_successful)

    def test_get_promotion_wisdom_for_fixture(self):
        """Should retrieve promotion wisdom for a fixture pattern."""
        self.brain.record_promotion(
            fixture_name="greeting_format",
            skill_name="kiro",
            proposal_types=["instruction"],
            reason="Safe change",
            confidence=0.85,
        )
        
        wisdom = self.brain.get_promotion_wisdom_for_fixture("greeting_format")
        self.assertEqual(len(wisdom), 1)
        self.assertEqual(wisdom[0].fixture_name, "greeting_format")

    def test_record_regression(self):
        """Should record regression patterns for prevention."""
        pattern = self.brain.record_regression(
            pattern_name="instruction_only_breaks_tests",
            skill_name="kiro",
            trigger="instruction proposal without test_case",
            fix_strategy="Require test_case proposals for risky fixtures",
            severity="critical",
        )
        
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.pattern_name, "instruction_only_breaks_tests")
        self.assertIn("kiro", pattern.observed_in_skills)
        self.assertEqual(pattern.severity, "critical")

    def test_record_regression_increments_occurrence(self):
        """Recording same regression in different skill should increment counter."""
        pattern1 = self.brain.record_regression(
            pattern_name="churn_overload",
            skill_name="skill_a",
            trigger="too many targets changed",
            fix_strategy="Enforce change budget",
        )
        
        pattern2 = self.brain.record_regression(
            pattern_name="churn_overload",
            skill_name="skill_b",
            trigger="too many targets changed",
            fix_strategy="Enforce change budget",
        )
        
        # Same pattern ID
        self.assertEqual(pattern1.id, pattern2.id)
        # Updated occurrence count
        self.assertEqual(pattern2.occurrence_count, 2)

    def test_get_regression_patterns_for_skill(self):
        """Should retrieve regression patterns specific to a skill."""
        self.brain.record_regression(
            pattern_name="slow_recovery",
            skill_name="weather",
            trigger="too many proposals at once",
            fix_strategy="Batch smaller changes",
        )
        
        patterns = self.brain.get_regression_patterns_for_skill("weather")
        self.assertGreater(len(patterns), 0)

    def test_add_fixture_to_library(self):
        """Should add fixture patterns to shared library."""
        template = {
            "name": "greeting_test",
            "input_data": {"name": "Alice"},
            "expected_output": {"greeting": "Hello, Alice!"},
        }
        
        entry = self.brain.add_fixture_to_library(
            fixture_pattern_name="formal_greeting",
            fixture_template=template,
            expected_behavior="Greet with formal salutation",
            successful_skills=["weather-brief", "kiro"],
        )
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.fixture_pattern_name, "formal_greeting")
        self.assertEqual(len(entry.successful_skills), 2)

    def test_get_similar_fixtures(self):
        """Should find similar fixture patterns in library."""
        self.brain.add_fixture_to_library(
            fixture_pattern_name="greeting_formal",
            fixture_template={},
            expected_behavior="Formal greeting",
            successful_skills=["weather"],
        )
        
        self.brain.add_fixture_to_library(
            fixture_pattern_name="farewell_formal",
            fixture_template={},
            expected_behavior="Formal farewell",
            successful_skills=["kiro"],
        )
        
        similar = self.brain.get_similar_fixtures("greeting_test")
        # Should find greeting_formal as most similar
        self.assertGreater(len(similar), 0)

    def test_get_or_create_skill_mastery(self):
        """Should get existing or create new skill mastery."""
        mastery1 = self.brain.get_or_create_skill_mastery("kiro", skill_type="mobile_app")
        self.assertEqual(mastery1.skill_name, "kiro")
        self.assertEqual(mastery1.skill_type, "mobile_app")
        
        # Should return same instance
        mastery2 = self.brain.get_or_create_skill_mastery("kiro", skill_type="mobile_app")
        self.assertEqual(mastery1.id, mastery2.id)

    def test_update_skill_mastery(self):
        """Should update skill mastery with trial results."""
        mastery = self.brain.get_or_create_skill_mastery("weather")
        mastery = self.brain.update_skill_mastery(
            "weather",
            total_trials=5,
            successful_promotions=3,
            most_effective_proposal_types=["test_case"],
        )
        
        self.assertEqual(mastery.total_trials, 5)
        self.assertEqual(mastery.successful_promotions, 3)
        self.assertIn("test_case", mastery.most_effective_proposal_types)

    def test_skill_mastery_persists_across_instances(self):
        """Skill mastery should persist to disk and reload correctly."""
        # Create mastery in first instance
        brain1 = SharedBrain(self.brain_dir)
        brain1.update_skill_mastery("kiro", total_trials=10)
        
        # Create new instance and verify persistence
        brain2 = SharedBrain(self.brain_dir)
        mastery = brain2.get_skill_mastery("kiro")
        self.assertEqual(mastery.total_trials, 10)

    def test_summarize_for_skill(self):
        """Should generate comprehensive skill summary from brain."""
        self.brain.get_or_create_skill_mastery("weather", skill_type="forecast")
        self.brain.update_skill_mastery("weather", total_trials=5, successful_promotions=3)
        
        summary = self.brain.summarize_for_skill("weather")
        
        self.assertEqual(summary["skill_name"], "weather")
        self.assertIsNotNone(summary["mastery"])
        self.assertGreater(len(summary["applicable_directives"]), 0)

    def test_brain_persistence_directives(self):
        """Directives should persist to disk."""
        directives_path = self.brain_dir / "core_directives.json"
        self.assertTrue(directives_path.exists())
        
        data = json.loads(directives_path.read_text())
        self.assertIn("cd_001_min_confidence", data)

    def test_brain_persistence_promotion_wisdom(self):
        """Promotion wisdom should persist to disk."""
        self.brain.record_promotion(
            fixture_name="test_fixture",
            skill_name="test_skill",
            proposal_types=["instruction"],
            reason="Good",
            confidence=0.85,
        )
        
        wisdom_path = self.brain_dir / "promotion_wisdom.json"
        self.assertTrue(wisdom_path.exists())
        
        data = json.loads(wisdom_path.read_text())
        self.assertGreater(len(data), 0)

    def test_brain_persistence_regression_patterns(self):
        """Regression patterns should persist to disk."""
        self.brain.record_regression(
            pattern_name="bad_pattern",
            skill_name="test_skill",
            trigger="too much change",
            fix_strategy="reduce change",
        )
        
        patterns_path = self.brain_dir / "regression_patterns.json"
        self.assertTrue(patterns_path.exists())
        
        data = json.loads(patterns_path.read_text())
        self.assertGreater(len(data), 0)

    def test_brain_persistence_skill_mastery(self):
        """Skill mastery should persist to disk."""
        self.brain.update_skill_mastery("test_skill", total_trials=5)
        
        mastery_path = self.brain_dir / "skill_mastery.json"
        self.assertTrue(mastery_path.exists())
        
        data = json.loads(mastery_path.read_text())
        self.assertIn("test_skill", data)

    def test_skill_mastery_fixture_insights_merge(self):
        """Fixture insights in mastery should merge, not replace."""
        self.brain.update_skill_mastery(
            "kiro",
            fixture_mastery={
                "greeting_test": {"pass_rate": 0.95},
            },
        )
        
        self.brain.update_skill_mastery(
            "kiro",
            fixture_mastery={
                "farewell_test": {"pass_rate": 0.87},
            },
        )
        
        mastery = self.brain.get_skill_mastery("kiro")
        self.assertEqual(len(mastery.fixture_mastery), 2)
        self.assertIn("greeting_test", mastery.fixture_mastery)
        self.assertIn("farewell_test", mastery.fixture_mastery)


if __name__ == "__main__":
    unittest.main()
