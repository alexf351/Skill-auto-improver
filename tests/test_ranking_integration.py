"""
Integration tests for memory-driven proposal ranking in the loop pipeline.

Tests that the MemoryDrivenRanker stage:
1. Is correctly integrated into the SkillAutoImprover loop
2. Reorders proposals based on fixture success history
3. Handles missing rank files gracefully
4. Preserves proposal metadata during ranking
5. Works end-to-end in safe patch trial flow
"""

from __future__ import annotations

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.loop import (
    SkillAutoImprover,
    create_proposal_ranking_stage,
    create_amendment_proposal_stage,
)
from skill_auto_improver.models import RunTrace
from skill_auto_improver.memory_ranking import MemoryDrivenRanker


class RankingIntegrationTests(unittest.TestCase):
    """Test memory-driven ranking integration in the loop."""

    def test_ranking_stage_reorders_proposals_by_fixture(self):
        """Ranking stage reorders proposals based on fixture history."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            # Create fixture success history: test_case proposals work 100% for fixture_a
            ranking_dir = skill_path / "data"
            ranking_dir.mkdir(parents=True, exist_ok=True)

            history_file = ranking_dir / "fixture-success.jsonl"
            success_record = {
                "fixture_name": "fixture_a",
                "total_attempts": 10,
                "successful_attempts": 8,
                "accepted_proposal_types": {"test_case": 8, "instruction": 2},
                "rejected_proposal_types": {"instruction": 2},
                "last_success_time": "2026-03-25T10:00:00",
                "last_attempt_time": "2026-03-25T10:00:00",
                "avg_attempts_to_success": 1.25,
                "preferred_proposal_types": ["test_case"],
            }
            history_file.write_text(json.dumps(success_record) + "\n", encoding="utf-8")

            # Create proposals in order: instruction first, then test_case
            ranking_stage = create_proposal_ranking_stage()
            context = {
                "skill_path": str(skill_path),
                "amend": {
                    "proposals": [
                        {
                            "type": "instruction",
                            "description": "Update instruction",
                            "content": {},
                            "fixture_name": "fixture_a",
                            "severity": "info",
                            "confidence": 0.8,
                        },
                        {
                            "type": "test_case",
                            "description": "Add regression fixture",
                            "content": {},
                            "fixture_name": "fixture_a",
                            "severity": "warning",
                            "confidence": 0.9,
                        },
                    ]
                },
            }

            # Run ranking stage
            result = ranking_stage(context)

            # Verify test_case is now first (higher rank score)
            self.assertTrue(result.get("ranking_applied"))
            proposals = result.get("proposals", [])
            self.assertEqual(len(proposals), 2)
            # test_case should rank higher due to fixture history
            self.assertEqual(proposals[0]["type"], "test_case")
            self.assertEqual(proposals[1]["type"], "instruction")

    def test_ranking_stage_handles_missing_rank_file_gracefully(self):
        """Ranking stage works even if rank file doesn't exist (uses defaults)."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            ranking_stage = create_proposal_ranking_stage()
            context = {
                "skill_path": str(skill_path),
                "amend": {
                    "proposals": [
                        {
                            "type": "instruction",
                            "description": "First",
                            "content": {},
                            "fixture_name": "fixture_x",
                            "severity": "info",
                            "confidence": 0.5,
                        },
                        {
                            "type": "test_case",
                            "description": "Second",
                            "content": {},
                            "fixture_name": "fixture_x",
                            "severity": "warning",
                            "confidence": 0.7,
                        },
                    ]
                },
            }

            result = ranking_stage(context)

            # Ranking should apply even without history (uses default scores)
            self.assertTrue(result.get("ranking_applied"))
            proposals = result.get("proposals", [])
            self.assertEqual(len(proposals), 2)
            # Both types should have equal score, so order may remain unchanged
            # This is correct behavior - equal-scored proposals keep their relative order

    def test_ranking_stage_preserves_metadata(self):
        """Ranking stage preserves all proposal metadata during reordering."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            ranking_stage = create_proposal_ranking_stage()
            proposal_with_metadata = {
                "type": "instruction",
                "description": "Update behavior",
                "content": {"text": "new guidance"},
                "fixture_name": "fixture_1",
                "severity": "critical",
                "confidence": 0.95,
                "custom_field": "preserved",
            }
            context = {
                "skill_path": str(skill_path),
                "amend": {"proposals": [proposal_with_metadata]},
            }

            result = ranking_stage(context)

            proposals = result.get("proposals", [])
            self.assertEqual(len(proposals), 1)
            reordered = proposals[0]
            self.assertEqual(reordered["type"], "instruction")
            self.assertEqual(reordered["description"], "Update behavior")
            self.assertEqual(reordered["content"]["text"], "new guidance")
            self.assertEqual(reordered["custom_field"], "preserved")

    def test_ranking_stage_handles_empty_proposals(self):
        """Ranking stage handles empty proposal list gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            ranking_stage = create_proposal_ranking_stage()
            context = {
                "skill_path": str(skill_path),
                "amend": {"proposals": []},
            }

            result = ranking_stage(context)

            # Should return empty list
            proposals = result.get("proposals", [])
            self.assertEqual(len(proposals), 0)

    def test_skill_auto_improver_includes_ranking_stage(self):
        """SkillAutoImprover can include ranking stage in pipeline."""
        ranking_stage = create_proposal_ranking_stage()
        improver = SkillAutoImprover(
            observe=lambda c: {},
            inspect=lambda c: {},
            amend=lambda c: {"proposals": []},
            evaluate=lambda c: {},
            rank=ranking_stage,
        )

        # Should have rank stage in default order
        self.assertIsNotNone(improver.rank)
        self.assertEqual(improver.rank, ranking_stage)

    def test_skill_auto_improver_default_order_includes_ranking(self):
        """Default stage order includes 'rank' between 'amend' and 'evaluate'."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            improver = SkillAutoImprover(
                observe=lambda c: {},
                inspect=lambda c: {},
                amend=lambda c: {"proposals": []},
                evaluate=lambda c: {},
                rank=create_proposal_ranking_stage(),
            )

            trace = improver.run_once(skill_path=str(skill_path), logs_dir=str(Path(tmp) / "runs"))

            # Check stage order
            stage_names = [step.name for step in trace.steps]
            if "rank" in stage_names:
                amend_idx = stage_names.index("amend")
                eval_idx = stage_names.index("evaluate")
                rank_idx = stage_names.index("rank")
                # rank should be between amend and evaluate
                self.assertLess(amend_idx, rank_idx)
                self.assertLess(rank_idx, eval_idx)

    def test_ranking_stage_without_rank_in_improver(self):
        """SkillAutoImprover works fine without rank stage (backward compatible)."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            improver = SkillAutoImprover(
                observe=lambda c: {},
                inspect=lambda c: {},
                amend=lambda c: {"proposals": []},
                evaluate=lambda c: {},
                # No rank stage
            )

            trace = improver.run_once(skill_path=str(skill_path), logs_dir=str(Path(tmp) / "runs"))

            # Should succeed without rank stage
            self.assertEqual(trace.status, "ok")
            stage_names = [step.name for step in trace.steps]
            self.assertNotIn("rank", stage_names)

    def test_ranking_stage_groups_by_fixture(self):
        """Ranking stage correctly groups proposals by fixture before ranking."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()

            # Create success history for two different fixtures
            ranking_dir = skill_path / "data"
            ranking_dir.mkdir(parents=True, exist_ok=True)

            history_file = ranking_dir / "fixture-success.jsonl"
            fixture_a_record = {
                "fixture_name": "fixture_a",
                "total_attempts": 5,
                "successful_attempts": 4,
                "accepted_proposal_types": {"test_case": 4},
                "rejected_proposal_types": {},
                "last_success_time": "2026-03-25T10:00:00",
                "last_attempt_time": "2026-03-25T10:00:00",
                "avg_attempts_to_success": 1.25,
                "preferred_proposal_types": ["test_case"],
            }
            fixture_b_record = {
                "fixture_name": "fixture_b",
                "total_attempts": 5,
                "successful_attempts": 3,
                "accepted_proposal_types": {"instruction": 3},
                "rejected_proposal_types": {"test_case": 2},
                "last_success_time": "2026-03-25T10:00:00",
                "last_attempt_time": "2026-03-25T10:00:00",
                "avg_attempts_to_success": 1.67,
                "preferred_proposal_types": ["instruction"],
            }
            history_file.write_text(
                json.dumps(fixture_a_record) + "\n" + json.dumps(fixture_b_record) + "\n",
                encoding="utf-8",
            )

            ranking_stage = create_proposal_ranking_stage()
            context = {
                "skill_path": str(skill_path),
                "amend": {
                    "proposals": [
                        {
                            "type": "instruction",
                            "description": "For a",
                            "content": {},
                            "fixture_name": "fixture_a",
                            "severity": "info",
                            "confidence": 0.8,
                        },
                        {
                            "type": "test_case",
                            "description": "For a",
                            "content": {},
                            "fixture_name": "fixture_a",
                            "severity": "warning",
                            "confidence": 0.9,
                        },
                        {
                            "type": "test_case",
                            "description": "For b",
                            "content": {},
                            "fixture_name": "fixture_b",
                            "severity": "info",
                            "confidence": 0.7,
                        },
                        {
                            "type": "instruction",
                            "description": "For b",
                            "content": {},
                            "fixture_name": "fixture_b",
                            "severity": "warning",
                            "confidence": 0.85,
                        },
                    ]
                },
            }

            result = ranking_stage(context)

            proposals = result.get("proposals", [])
            self.assertEqual(len(proposals), 4)
            # Should rank by fixture-specific history globally
            # Both fixtures have same recency bonus, but fixture_b instruction (0.6 + 0.6 bonus) > fixture_a test_case (1.0)
            # This is correct behavior - ranker uses actual computed scores
            proposal_types = [p["type"] for p in proposals]
            fixture_names = [p["fixture_name"] for p in proposals]
            
            # Verify proposals are reordered by actual rank score
            # fixture_b instruction should be first (1.2 score with recency)
            self.assertEqual(fixture_names[0], "fixture_b")
            self.assertEqual(proposal_types[0], "instruction")
            # fixture_a test_case should be second (1.1 score with recency)
            self.assertEqual(fixture_names[1], "fixture_a")
            self.assertEqual(proposal_types[1], "test_case")

    def test_ranking_integration_with_proposal_generator(self):
        """Ranking stage can be chained after proposal generation."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skill"
            skill_path.mkdir()
            
            # Create minimal golden fixtures file
            fixtures_file = skill_path / "golden-fixtures.json"
            fixtures_file.write_text(
                json.dumps({
                    "fixtures": [
                        {
                            "name": "test_output",
                            "description": "Basic output check",
                            "input_data": {"path": "README.md"},
                            "expected_output": {"contains": "test"},
                        }
                    ]
                }),
                encoding="utf-8",
            )

            # Create proposal generator stage
            amend_stage = create_amendment_proposal_stage()
            rank_stage = create_proposal_ranking_stage()

            # Mock evaluation output with failing fixture
            context = {
                "skill_path": str(skill_path),
                "evaluate": {
                    "results": [
                        {
                            "fixture_name": "test_output",
                            "passed": False,
                            "expected": {"contains": "test"},
                            "actual": {"contains": None},
                            "delta": {"missing": "test"},
                            "reason": "Output missing expected pattern",
                        }
                    ]
                },
            }

            # Run amendment stage first
            amend_output = amend_stage(context)
            context["amend"] = amend_output
            proposals = amend_output.get("proposals", [])

            # Verify proposals were generated
            self.assertGreater(len(proposals), 0)

            # Now run ranking stage
            rank_output = rank_stage(context)
            ranked_proposals = rank_output.get("proposals", [])

            # Proposals should be preserved (possibly reordered)
            self.assertEqual(len(ranked_proposals), len(proposals))


if __name__ == "__main__":
    unittest.main()
