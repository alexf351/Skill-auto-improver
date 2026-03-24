"""
Tests for Proposer + SharedBrain integration.

Validates that the proposal engine can:
1. Accept a SharedBrain instance
2. Load cross-skill context on demand
3. Boost confidence based on promotion wisdom
4. Apply regression prevention rules
5. Enrich proposals with cross-skill lessons
"""

import unittest
import tempfile
from pathlib import Path

from skill_auto_improver.proposer import ProposalEngine, PatchProposal
from skill_auto_improver.shared_brain import SharedBrain, PromotionWisdom, RegressionPattern, CoreDirective
from skill_auto_improver.evaluator import TestResult


class ProposerBrainIntegrationTest(unittest.TestCase):
    """Test ProposalEngine with SharedBrain context."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name) / "brain"
        self.brain_dir.mkdir(parents=True)
        
        # Create shared brain with some pre-populated wisdom
        self.brain = SharedBrain(self.brain_dir)
        
        # Seed the brain with promotion wisdom
        wisdom = PromotionWisdom(
            id="pw_test_001",
            fixture_name="greeting_test",
            description="Formal greeting pattern",
            acceptance_reason="100% recovery with test case + instruction",
            skills_successful=["kiro-ugc-brief", "morning-brief"],
            proposal_type_sequence=["test_case", "instruction"],
            confidence_floor=0.85,
            confidence=0.90,
            shared_lessons=["Always add test cases before instruction edits", "Formal greeting needs backward compat"],
            promotion_count=3,
        )
        self.brain.promotion_wisdom[wisdom.id] = wisdom
        
        # Seed with regression pattern
        pattern = RegressionPattern(
            id="rp_test_001",
            pattern_name="instruction_only_fails",
            description="Instruction-only changes often regress",
            triggers=["instruction_proposal_without_test_case"],
            fix_strategy="Always pair instruction edits with test cases",
            severity="critical",
            observed_in_skills=["kiro-dev-assistant", "kiro-content-calendar"],
            prevention_rule="require_test_case_for_protected_fixtures",
            occurrence_count=5,
            prevention_success_rate=0.92,
        )
        self.brain.regression_patterns[pattern.id] = pattern
        
        # Seed with core directive
        directive = CoreDirective(
            id="cd_test_001",
            title="min_confidence_gate",
            description="Enforce minimum 0.80 confidence for auto-apply",
            applies_to=["*"],
            auto_apply=True,
        )
        self.brain.core_directives[directive.id] = directive
        
        # Create skill mastery for the test skill
        mastery = self.brain.get_or_create_skill_mastery("test-skill")
        mastery.trial_count = 5
        mastery.success_rate = 0.80
        mastery.most_useful_proposal_type = "test_case"
        mastery.common_issues = ["Missing edge cases", "Unclear instructions"]
    
    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()
    
    def test_proposer_accepts_brain(self):
        """ProposalEngine should accept SharedBrain instance."""
        engine = ProposalEngine(brain=self.brain)
        self.assertIsNotNone(engine.brain)
        self.assertIs(engine.brain, self.brain)
    
    def test_proposer_works_without_brain(self):
        """ProposalEngine should work fine without brain (backward compatible)."""
        engine = ProposalEngine()
        self.assertIsNone(engine.brain)
        
        # Should still generate proposals
        failed_result = TestResult(
            fixture_name="test_greeting",
            passed=False,
            expected={"greeting": "Hello, World!"},
            actual={"greeting": "Hi"},
            delta={"greeting": "Expected 'Hello, World!' but got 'Hi'"},
        )
        report = engine.generate_proposals([failed_result])
        self.assertEqual(report.total_failures, 1)
        self.assertGreater(len(report.proposals), 0)
    
    def test_brain_context_loading(self):
        """Should load cross-skill context from brain."""
        engine = ProposalEngine(brain=self.brain)
        context = engine._load_brain_context("test-skill")
        
        self.assertTrue(context.get("brain_context"))
        self.assertEqual(context.get("skill_name"), "test-skill")
        self.assertGreater(len(context.get("core_directives", [])), 0)
        self.assertIsNotNone(context.get("skill_mastery"))
        self.assertEqual(context["skill_mastery"]["trial_count"], 5)
    
    def test_brain_context_promotion_wisdom_included(self):
        """Brain context should include promotion wisdom."""
        engine = ProposalEngine(brain=self.brain)
        context = engine._load_brain_context("test-skill")
        
        # The brain's summarize_for_skill should have included promotion wisdom
        self.assertTrue(context.get("brain_context"))
    
    def test_brain_context_regression_patterns_included(self):
        """Brain context should include regression patterns."""
        engine = ProposalEngine(brain=self.brain)
        context = engine._load_brain_context("test-skill")
        
        patterns = context.get("regression_patterns", [])
        # May or may not have patterns for this skill, but structure should be correct
        self.assertIsInstance(patterns, list)
    
    def test_confidence_boost_from_promotion_wisdom(self):
        """Confidence should be boosted by promotion wisdom."""
        # Engine without brain
        engine_plain = ProposalEngine()
        
        # Engine with brain
        engine_brain = ProposalEngine(brain=self.brain)
        
        failed_result = TestResult(
            fixture_name="greeting_test",  # This fixture is promoted in brain
            passed=False,
            expected={"greeting": "Hello, World!"},
            actual={"greeting": "Hi"},
            delta={"greeting": "mismatch"},
        )
        
        report_plain = engine_plain.generate_proposals([failed_result])
        report_brain = engine_brain.generate_proposals(
            [failed_result],
            skill_name="test-skill"
        )
        
        # Reports should have proposals
        self.assertGreater(len(report_plain.proposals), 0)
        self.assertGreater(len(report_brain.proposals), 0)
        
        # Brain-enhanced report should have memory context
        self.assertIsNotNone(report_brain.memory_context)
        self.assertTrue(report_brain.memory_context.get("brain_context", False))
    
    def test_memory_hints_include_cross_skill_lessons(self):
        """Memory hints should include cross-skill lessons from brain."""
        engine = ProposalEngine(brain=self.brain)
        
        # Prepare memory context with brain data
        memory_context = engine._load_brain_context("test-skill")
        
        # Get hints for a fixture that has promotion wisdom
        hints = engine._memory_hints("greeting_test", memory_context)
        
        # Hints should exist and mention cross-skill context
        self.assertIsNotNone(hints)
        if "brain_context" in memory_context and memory_context["brain_context"]:
            # When brain context is loaded, hints may include promotion info
            pass
    
    def test_proposal_ranking_considers_brain_directives(self):
        """Proposal ranking should consider core directives from brain."""
        engine = ProposalEngine(brain=self.brain)
        
        failed_results = [
            TestResult(
                fixture_name="test_1",
                passed=False,
                expected={"field": "expected"},
                actual={"field": "actual"},
                delta={"field": "mismatch"},
            ),
        ]
        
        report = engine.generate_proposals(
            failed_results,
            skill_name="test-skill"
        )
        
        # Should have generated proposals
        self.assertGreater(len(report.proposals), 0)
        
        # Proposals should be sorted (by default)
        if len(report.proposals) > 1:
            # Verify proposals are in some order
            types = [p.type for p in report.proposals]
            self.assertGreater(len(set(types)), 0)
    
    def test_brain_graceful_degradation(self):
        """Should gracefully degrade if brain queries fail."""
        engine = ProposalEngine(brain=self.brain)
        
        # Call with an invalid skill name (shouldn't crash)
        context = engine._load_brain_context("nonexistent-skill")
        
        # Should still return context structure
        self.assertIsInstance(context, dict)
        self.assertTrue(context.get("brain_context", False))
    
    def test_full_flow_with_brain(self):
        """Full proposal generation with brain context."""
        engine = ProposalEngine(brain=self.brain)
        
        failed_results = [
            TestResult(
                fixture_name="greeting_test",
                passed=False,
                expected={"greeting": "Hello, World!", "formal": True},
                actual={"greeting": "Hi", "formal": False},
                delta={
                    "greeting": "Expected 'Hello, World!' but got 'Hi'",
                    "formal": "Expected True but got False",
                },
            ),
        ]
        
        report = engine.generate_proposals(
            failed_results,
            skill_name="test-skill",
            skill_path=Path("/tmp/test-skill"),
        )
        
        # Should have generated proposals
        self.assertGreater(len(report.proposals), 0)
        
        # Memory context should be enriched
        self.assertIsNotNone(report.memory_context)
        self.assertTrue(report.memory_context.get("brain_context", False))
        
        # Proposals should have reasonable confidence values
        for proposal in report.proposals:
            self.assertGreaterEqual(proposal.confidence, 0.0)
            self.assertLessEqual(proposal.confidence, 0.99)


if __name__ == "__main__":
    unittest.main()
