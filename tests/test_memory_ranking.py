"""
Unit tests for memory-driven proposal ranking.
"""

import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

from skill_auto_improver.memory_ranking import (
    FixtureSuccessRecord,
    FixtureSimilarity,
    MemoryDrivenRanker,
)


@dataclass
class MockProposal:
    """Mock proposal for testing."""
    type: str
    fixture_name: str
    description: str = "test"
    confidence: float = 0.8


class FixtureSuccessRecordTests(unittest.TestCase):
    """Tests for FixtureSuccessRecord."""

    def test_fixture_success_record_init(self):
        """Should initialize with fixture name."""
        record = FixtureSuccessRecord(fixture_name="test_fixture")
        self.assertEqual(record.fixture_name, "test_fixture")
        self.assertEqual(record.total_attempts, 0)
        self.assertEqual(record.success_rate, 0.5)  # neutral default

    def test_record_acceptance_increments_counters(self):
        """Should increment success counters on acceptance."""
        record = FixtureSuccessRecord(fixture_name="api_get")
        record.record_acceptance("test_case")

        self.assertEqual(record.total_attempts, 1)
        self.assertEqual(record.successful_attempts, 1)
        self.assertEqual(record.accepted_proposal_types["test_case"], 1)
        self.assertAlmostEqual(record.success_rate, 1.0)

    def test_record_rejection_increments_attempt_only(self):
        """Should increment total attempts on rejection."""
        record = FixtureSuccessRecord(fixture_name="api_get")
        record.record_rejection("instruction")

        self.assertEqual(record.total_attempts, 1)
        self.assertEqual(record.successful_attempts, 0)
        self.assertEqual(record.rejected_proposal_types["instruction"], 1)
        self.assertEqual(record.success_rate, 0.0)

    def test_acceptance_rate_with_mixed_outcomes(self):
        """Should calculate acceptance rate correctly."""
        record = FixtureSuccessRecord(fixture_name="edge_case_1")
        record.record_acceptance("test_case")
        record.record_acceptance("test_case")
        record.record_rejection("test_case")

        rate = record.get_acceptance_rate("test_case")
        self.assertAlmostEqual(rate, 2.0 / 3.0, places=2)

    def test_acceptance_rate_neutral_for_unknown_type(self):
        """Should return 0.5 (neutral) for unknown proposal types."""
        record = FixtureSuccessRecord(fixture_name="unknown")
        rate = record.get_acceptance_rate("never_seen_this_type")
        self.assertEqual(rate, 0.5)

    def test_preferred_proposal_types_ordered_by_success(self):
        """Should rank preferred types by acceptance rate."""
        record = FixtureSuccessRecord(fixture_name="mixed")
        
        # test_case: 3/4 = 0.75
        record.record_acceptance("test_case")
        record.record_acceptance("test_case")
        record.record_acceptance("test_case")
        record.record_rejection("test_case")
        
        # instruction: 1/3 = 0.33
        record.record_acceptance("instruction")
        record.record_rejection("instruction")
        record.record_rejection("instruction")

        self.assertEqual(record.preferred_proposal_types[0], "test_case")
        self.assertEqual(record.preferred_proposal_types[1], "instruction")

    def test_is_historically_difficult_with_high_attempts(self):
        """Should mark as difficult if avg_attempts_to_success > 2.0."""
        record = FixtureSuccessRecord(fixture_name="tricky")
        record.record_acceptance("instruction")
        record.record_rejection("instruction")
        record.record_rejection("test_case")
        record.record_acceptance("test_case")
        record.record_rejection("artifact")
        record.record_acceptance("artifact")
        
        # 3 successes out of 6 attempts = 2.0 attempts per success
        record._recalc_avg_attempts()
        self.assertGreaterEqual(record.avg_attempts_to_success, 2.0)
        self.assertTrue(record.is_historically_difficult)

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        record = FixtureSuccessRecord(fixture_name="api_post")
        record.record_acceptance("test_case")
        record.record_rejection("instruction")
        record.last_success_time = datetime.utcnow().isoformat()

        data = record.to_dict()
        restored = FixtureSuccessRecord.from_dict(data)

        self.assertEqual(restored.fixture_name, record.fixture_name)
        self.assertEqual(restored.total_attempts, record.total_attempts)
        self.assertEqual(restored.successful_attempts, record.successful_attempts)
        self.assertEqual(restored.accepted_proposal_types, record.accepted_proposal_types)


class FixtureSimilarityTests(unittest.TestCase):
    """Tests for FixtureSimilarity."""

    def test_fixture_similarity_init(self):
        """Should initialize with fixture pair and score."""
        sim = FixtureSimilarity(
            fixture_a="api_get",
            fixture_b="api_post",
            similarity_score=0.7,
            shared_traits=["api", "http"],
        )
        self.assertEqual(sim.fixture_a, "api_get")
        self.assertEqual(sim.fixture_b, "api_post")
        self.assertEqual(sim.similarity_score, 0.7)

    def test_fixture_similarity_lt_compares_descending(self):
        """Should sort by similarity ascending (for normal sorted())."""
        sim1 = FixtureSimilarity("a", "b", 0.9)
        sim2 = FixtureSimilarity("a", "c", 0.5)
        
        # sim1 < sim2 should be False (0.9 is not < 0.5)
        self.assertFalse(sim1 < sim2)
        self.assertTrue(sim2 < sim1)


class MemoryDrivenRankerTests(unittest.TestCase):
    """Tests for MemoryDrivenRanker."""

    def test_ranker_init_without_memory_dir(self):
        """Should initialize without memory directory."""
        ranker = MemoryDrivenRanker()
        self.assertEqual(len(ranker.success_records), 0)

    def test_ranker_init_with_nonexistent_memory_dir(self):
        """Should gracefully handle missing memory directory."""
        ranker = MemoryDrivenRanker(memory_dir="/nonexistent/path")
        self.assertEqual(len(ranker.success_records), 0)

    def test_ranker_loads_existing_success_records(self):
        """Should load success records from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create memory structure
            memory_dir = Path(tmpdir)
            data_dir = memory_dir / "data"
            data_dir.mkdir(parents=True)

            # Write a fixture record
            record = FixtureSuccessRecord(fixture_name="api_get")
            record.record_acceptance("test_case")
            record.record_rejection("instruction")

            records_path = data_dir / "fixture-success.jsonl"
            with open(records_path, "w") as f:
                f.write(json.dumps(record.to_dict()) + "\n")

            # Load and verify
            ranker = MemoryDrivenRanker(memory_dir=memory_dir)
            self.assertEqual(len(ranker.success_records), 1)
            self.assertIn("api_get", ranker.success_records)

    def test_record_proposal_outcome_acceptance(self):
        """Should track proposal acceptance."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("fixture_a", "test_case", accepted=True)

        self.assertIn("fixture_a", ranker.success_records)
        record = ranker.success_records["fixture_a"]
        self.assertEqual(record.accepted_proposal_types["test_case"], 1)
        self.assertEqual(record.total_attempts, 1)

    def test_record_proposal_outcome_rejection(self):
        """Should track proposal rejection."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("fixture_b", "instruction", accepted=False)

        record = ranker.success_records["fixture_b"]
        self.assertEqual(record.rejected_proposal_types["instruction"], 1)
        self.assertEqual(record.total_attempts, 1)

    def test_rank_proposals_empty_list(self):
        """Should handle empty proposal list."""
        ranker = MemoryDrivenRanker()
        result = ranker.rank_proposals([], "unknown_fixture")
        self.assertEqual(len(result), 0)

    def test_rank_proposals_single_proposal(self):
        """Should rank a single proposal."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("test_fix", "test_case", accepted=True)

        proposals = [MockProposal(type="test_case", fixture_name="test_fix")]
        ranked = ranker.rank_proposals(proposals, "test_fix")

        self.assertEqual(len(ranked), 1)
        proposal, score = ranked[0]
        self.assertEqual(proposal.type, "test_case")
        self.assertGreater(score, 0.5)

    def test_rank_proposals_multiple_proposals_orders_by_success(self):
        """Should order proposals by success history."""
        ranker = MemoryDrivenRanker()
        
        # test_case has 2/2 success
        ranker.record_proposal_outcome("fixture", "test_case", accepted=True)
        ranker.record_proposal_outcome("fixture", "test_case", accepted=True)
        
        # instruction has 0/2 failures
        ranker.record_proposal_outcome("fixture", "instruction", accepted=False)
        ranker.record_proposal_outcome("fixture", "instruction", accepted=False)

        proposals = [
            MockProposal(type="instruction", fixture_name="fixture"),
            MockProposal(type="test_case", fixture_name="fixture"),
        ]
        ranked = ranker.rank_proposals(proposals, "fixture")

        # test_case should rank higher
        self.assertEqual(ranked[0][0].type, "test_case")
        self.assertEqual(ranked[1][0].type, "instruction")
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_rank_proposals_recency_bonus(self):
        """Should apply recency bonus to recent successes."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("recent_fix", "test_case", accepted=True)
        
        # Manually set recent success time
        record = ranker.success_records["recent_fix"]
        record.last_success_time = datetime.utcnow().isoformat()

        proposals = [MockProposal(type="test_case", fixture_name="recent_fix")]
        ranked = ranker.rank_proposals(proposals, "recent_fix")

        proposal, score = ranked[0]
        # Score should include recency bonus (0.5 + 0.1 ≈ 0.6)
        self.assertGreater(score, 0.55)

    def test_find_similar_fixtures_by_base(self):
        """Should find similar fixtures by shared base name."""
        ranker = MemoryDrivenRanker()
        ranker.success_records["api_get"] = FixtureSuccessRecord("api_get")
        ranker.success_records["api_post"] = FixtureSuccessRecord("api_post")
        ranker.success_records["db_query"] = FixtureSuccessRecord("db_query")

        similar = ranker._find_similar_fixtures("api_delete")

        # Should find api_get and api_post as similar
        similar_names = [s.fixture_b for s in similar]
        self.assertIn("api_get", similar_names)
        self.assertIn("api_post", similar_names)
        self.assertNotIn("db_query", similar_names)

    def test_rank_proposals_borrows_from_similar(self):
        """Should use similar fixtures' success to guide ranking."""
        ranker = MemoryDrivenRanker()
        
        # Similar fixture (api_get) has success with test_case
        ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
        ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
        ranker.record_proposal_outcome("api_get", "instruction", accepted=False)
        
        # New fixture (api_post) has no history
        # But should borrow api_get's success pattern

        proposals = [
            MockProposal(type="instruction", fixture_name="api_post"),
            MockProposal(type="test_case", fixture_name="api_post"),
        ]
        ranked = ranker.rank_proposals(proposals, "api_post")

        # test_case should rank higher due to similarity borrowing
        self.assertEqual(ranked[0][0].type, "test_case")

    def test_save_success_records_persists_to_disk(self):
        """Should save success records to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ranker = MemoryDrivenRanker()
            ranker.record_proposal_outcome("fixture_x", "test_case", accepted=True)

            memory_dir = Path(tmpdir)
            ranker.save_success_records(memory_dir)

            # Verify file was created
            records_path = memory_dir / "data" / "fixture-success.jsonl"
            self.assertTrue(records_path.exists())

            # Verify content
            with open(records_path) as f:
                line = f.readline()
                data = json.loads(line)
                self.assertEqual(data["fixture_name"], "fixture_x")

    def test_summary_empty_ranker(self):
        """Should return empty summary for new ranker."""
        ranker = MemoryDrivenRanker()
        summary = ranker.summary()

        self.assertEqual(summary["total_fixtures"], 0)
        self.assertEqual(len(summary["fixtures_tracked"]), 0)

    def test_summary_with_fixtures(self):
        """Should provide comprehensive summary."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("easy", "test_case", accepted=True)
        ranker.record_proposal_outcome("easy", "test_case", accepted=True)
        ranker.record_proposal_outcome("hard", "instruction", accepted=False)
        ranker.record_proposal_outcome("hard", "instruction", accepted=False)
        ranker.record_proposal_outcome("hard", "test_case", accepted=True)

        summary = ranker.summary()

        self.assertEqual(summary["total_fixtures"], 2)
        self.assertIn("easy", summary["fixtures_tracked"])
        self.assertIn("hard", summary["fixtures_tracked"])
        self.assertGreater(summary["avg_success_rate"], 0.0)
        self.assertIn("fixture_details", summary)

    def test_rank_proposals_filters_by_fixture_name(self):
        """Should only rank proposals matching the target fixture."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("fixture_a", "test_case", accepted=True)

        proposals = [
            MockProposal(type="test_case", fixture_name="fixture_a"),
            MockProposal(type="instruction", fixture_name="fixture_b"),  # Different fixture
        ]
        ranked = ranker.rank_proposals(proposals, "fixture_a")

        # Should only include fixture_a proposal
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0][0].fixture_name, "fixture_a")

    def test_compute_rank_score_caps_at_two(self):
        """Should cap rank score at ~2.0 for stable sorting."""
        ranker = MemoryDrivenRanker()
        ranker.record_proposal_outcome("fixture", "test_case", accepted=True)

        record = ranker.success_records["fixture"]
        similar = ranker._find_similar_fixtures("fixture")

        proposal = MockProposal(type="test_case", fixture_name="fixture")
        score = ranker._compute_rank_score(proposal, record, similar)

        self.assertLessEqual(score, 2.0)

    def test_difficulty_adjustment_boosts_reliable_types(self):
        """Should boost score for reliable types on difficult fixtures."""
        ranker = MemoryDrivenRanker()
        
        # Make a difficult fixture: 3 successes out of 6 attempts
        for _ in range(3):
            ranker.record_proposal_outcome("difficult", "test_case", accepted=True)
        for _ in range(3):
            ranker.record_proposal_outcome("difficult", "instruction", accepted=False)

        record = ranker.success_records["difficult"]
        record._recalc_avg_attempts()

        # test_case (100% success) should get boost
        proposal = MockProposal(type="test_case", fixture_name="difficult")
        similar = ranker._find_similar_fixtures("difficult")
        score = ranker._compute_rank_score(proposal, record, similar)

        self.assertGreater(score, 0.75)  # Should be boosted


if __name__ == "__main__":
    unittest.main()
