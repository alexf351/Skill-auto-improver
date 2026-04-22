import tempfile
import unittest
from pathlib import Path

from skill_auto_improver.promotion_rules import PromotionRulesEngine
from skill_auto_improver.proposer import PatchProposal
from skill_auto_improver.shared_brain import PromotionWisdom


class PromotionRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name) / "brain"
        self.engine = PromotionRulesEngine(self.brain_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_learn_from_promotion_creates_rule_for_cross_skill_high_confidence_wisdom(self):
        wisdom = PromotionWisdom(
            id="pw_greeting",
            fixture_name="formal_greeting",
            description="formal greeting pattern works safely",
            acceptance_reason="safe improvement",
            skills_successful=["skill-a", "skill-b"],
            proposal_type_sequence=["instruction"],
            confidence_floor=0.85,
            confidence=0.91,
            promotion_count=2,
        )

        self.engine.learn_from_promotion(wisdom)

        self.assertEqual(len(self.engine.rules), 1)
        rule = self.engine.rules[0]
        self.assertEqual(rule.fixture_pattern, "formal_greeting")
        self.assertEqual(rule.proposal_type, "instruction")
        self.assertTrue(self.engine.rules_file.exists())
        self.assertIn("last_updated", self.engine.rules_file.read_text())

    def test_evaluate_proposal_auto_applies_when_rule_matches_patch_proposal(self):
        wisdom = PromotionWisdom(
            id="pw_greeting",
            fixture_name="formal_greeting",
            description="formal greeting pattern works safely",
            acceptance_reason="safe improvement",
            skills_successful=["skill-a", "skill-b"],
            proposal_type_sequence=["instruction"],
            confidence_floor=0.85,
            confidence=0.93,
            promotion_count=3,
        )
        self.engine.learn_from_promotion(wisdom)

        proposal = PatchProposal(
            type="instruction",
            description="tighten greeting instructions",
            content={"suggestion": "Be formal"},
            fixture_name="formal_greeting",
            confidence=0.88,
        )

        decision = self.engine.evaluate_proposal(proposal, "demo-skill", [wisdom])

        self.assertTrue(decision.should_auto_apply)
        self.assertIsNotNone(decision.rule_matched)
        self.assertEqual(decision.matched_wisdom.id, wisdom.id)

    def test_evaluate_proposal_escalates_when_no_wisdom_matches(self):
        proposal = PatchProposal(
            type="instruction",
            description="tighten greeting instructions",
            content={"suggestion": "Be formal"},
            fixture_name="formal_greeting",
            confidence=0.88,
        )

        decision = self.engine.evaluate_proposal(proposal, "demo-skill", [])

        self.assertFalse(decision.should_auto_apply)
        self.assertTrue(decision.escalation_required)
        self.assertIn("No promotion rules configured", decision.escalation_reason)

    def test_summarize_dashboard_returns_rule_counts_and_top_rules(self):
        wisdom = PromotionWisdom(
            id="pw_greeting",
            fixture_name="formal_greeting",
            description="formal greeting pattern works safely",
            acceptance_reason="safe improvement",
            skills_successful=["skill-a", "skill-b"],
            proposal_type_sequence=["instruction"],
            confidence_floor=0.85,
            confidence=0.92,
            promotion_count=2,
        )

        self.engine.learn_from_promotion(wisdom)
        dashboard = self.engine.summarize_dashboard(limit=3)

        self.assertEqual(dashboard["counts"]["total"], 1)
        self.assertEqual(dashboard["counts"]["enabled"], 1)
        self.assertEqual(dashboard["counts"]["auto_apply"], 1)
        self.assertEqual(dashboard["top_auto_apply_rules"][0]["fixture_pattern"], "formal_greeting")
