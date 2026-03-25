#!/usr/bin/env python3
"""
Memory-Driven Proposal Ranking Demo

Shows how proposals are reordered based on per-fixture success history.

Demonstrates:
1. Tracking proposal acceptance/rejection over time
2. Ranking proposals by success likelihood
3. Borrowing success patterns from similar fixtures
4. Handling new/unknown fixtures gracefully
5. Persistence across sessions
"""

import sys
from pathlib import Path
from dataclasses import dataclass

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skill_auto_improver.memory_ranking import (
    MemoryDrivenRanker,
    FixtureSuccessRecord,
)


@dataclass
class ProposalStub:
    """Minimal proposal for demo."""
    type: str
    fixture_name: str
    description: str = "Test proposal"


def demo_scenario_1_basic_ranking():
    """Scenario 1: Basic ranking based on direct success history."""
    print("\n" + "=" * 70)
    print("SCENARIO 1: Basic Ranking Based on Success History")
    print("=" * 70)

    ranker = MemoryDrivenRanker()

    # Build history: api_get fixture has strong test_case success, weak instruction
    print("\n📝 Building history for 'api_get' fixture:")
    ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_get", "instruction", accepted=False)
    ranker.record_proposal_outcome("api_get", "instruction", accepted=False)
    
    record = ranker.success_records["api_get"]
    print(f"  - test_case: {record.get_acceptance_rate('test_case'):.0%} success (3/3)")
    print(f"  - instruction: {record.get_acceptance_rate('instruction'):.0%} success (0/2)")

    # Now rank new proposals for this fixture
    proposals = [
        ProposalStub(type="instruction", fixture_name="api_get", description="Update SKILL.md"),
        ProposalStub(type="test_case", fixture_name="api_get", description="Add regression test"),
    ]

    print("\n🎯 Ranking proposals for 'api_get':")
    ranked = ranker.rank_proposals(proposals, "api_get")
    for rank, (proposal, score) in enumerate(ranked, 1):
        print(f"  {rank}. {proposal.type:15} (score: {score:.3f}) - {proposal.description}")

    print("\n✓ Result: test_case ranked higher due to 100% historical success rate")


def demo_scenario_2_similarity_borrowing():
    """Scenario 2: New fixture borrows success from similar ones."""
    print("\n" + "=" * 70)
    print("SCENARIO 2: Similarity Borrowing (New Fixture Learning from Similar)")
    print("=" * 70)

    ranker = MemoryDrivenRanker()

    # Build history for similar fixtures
    print("\n📝 Building history for similar API fixtures:")
    
    # api_get: test_case works well
    ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_get", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_get", "instruction", accepted=False)
    
    # api_list: test_case also works well
    ranker.record_proposal_outcome("api_list", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_list", "test_case", accepted=True)
    ranker.record_proposal_outcome("api_list", "instruction", accepted=False)
    
    print("  - api_get:  test_case 100% success, instruction 0%")
    print("  - api_list: test_case 100% success, instruction 0%")

    # Now introduce a new fixture (no history)
    print("\n🆕 New fixture 'api_delete' (no history yet):")
    proposals = [
        ProposalStub(type="instruction", fixture_name="api_delete", description="Update SKILL.md"),
        ProposalStub(type="test_case", fixture_name="api_delete", description="Add regression test"),
    ]

    print("\n🎯 Ranking proposals for 'api_delete' (borrows from similar):")
    ranked = ranker.rank_proposals(proposals, "api_delete")
    for rank, (proposal, score) in enumerate(ranked, 1):
        print(f"  {rank}. {proposal.type:15} (score: {score:.3f}) - {proposal.description}")

    print("\n✓ Result: test_case ranked higher due to 100% success in similar fixtures")
    print("  (api_get and api_list both show test_case works well)")


def demo_scenario_3_difficult_fixtures():
    """Scenario 3: Difficult fixtures boost reliable proposal types."""
    print("\n" + "=" * 70)
    print("SCENARIO 3: Difficult Fixture Preference for Reliable Types")
    print("=" * 70)

    ranker = MemoryDrivenRanker()

    print("\n📝 Building history for 'edge_case_validation' (difficult fixture):")
    print("  Many attempts, only test_case proposals work reliably:")
    
    # Many attempts, only test_case works
    for _ in range(2):
        ranker.record_proposal_outcome("edge_case_validation", "test_case", accepted=True)
    for _ in range(4):
        ranker.record_proposal_outcome("edge_case_validation", "instruction", accepted=False)
    for _ in range(2):
        ranker.record_proposal_outcome("edge_case_validation", "artifact", accepted=False)
    
    record = ranker.success_records["edge_case_validation"]
    print(f"  - test_case: {record.get_acceptance_rate('test_case'):.0%} success (2/2)")
    print(f"  - instruction: {record.get_acceptance_rate('instruction'):.0%} success (0/4)")
    print(f"  - artifact: {record.get_acceptance_rate('artifact'):.0%} success (0/2)")
    print(f"  - Difficulty: {record.avg_attempts_to_success:.1f} attempts per success")

    # Rank proposals
    proposals = [
        ProposalStub(type="instruction", fixture_name="edge_case_validation"),
        ProposalStub(type="artifact", fixture_name="edge_case_validation"),
        ProposalStub(type="test_case", fixture_name="edge_case_validation"),
    ]

    print("\n🎯 Ranking proposals (difficult fixture)::")
    ranked = ranker.rank_proposals(proposals, "edge_case_validation")
    for rank, (proposal, score) in enumerate(ranked, 1):
        print(f"  {rank}. {proposal.type:15} (score: {score:.3f})")

    print("\n✓ Result: test_case ranked first (highest reliability on difficult fixture)")


def demo_scenario_4_persistence():
    """Scenario 4: Persistence across sessions."""
    print("\n" + "=" * 70)
    print("SCENARIO 4: Persistence Across Sessions")
    print("=" * 70)

    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_dir = Path(tmpdir)
        
        # Session 1: Build history
        print("\n💾 Session 1: Building history")
        ranker1 = MemoryDrivenRanker()
        ranker1.record_proposal_outcome("parser_json", "test_case", accepted=True)
        ranker1.record_proposal_outcome("parser_json", "instruction", accepted=False)
        ranker1.save_success_records(memory_dir)
        
        print(f"  - Recorded 2 proposals for 'parser_json'")
        print(f"  - Saved to {memory_dir / 'data' / 'fixture-success.jsonl'}")

        # Session 2: Load and reuse
        print("\n💾 Session 2: Loading persisted history")
        ranker2 = MemoryDrivenRanker(memory_dir=memory_dir)
        
        record = ranker2.success_records.get("parser_json")
        if record:
            print(f"  ✓ Loaded history for 'parser_json'")
            print(f"    - test_case: {record.get_acceptance_rate('test_case'):.0%} success")
            print(f"    - instruction: {record.get_acceptance_rate('instruction'):.0%} success")
        else:
            print(f"  ✗ History not found!")

        # Rank with persisted history
        proposals = [
            ProposalStub(type="instruction", fixture_name="parser_json"),
            ProposalStub(type="test_case", fixture_name="parser_json"),
        ]
        
        print("\n🎯 Ranking proposals (using persisted history):")
        ranked = ranker2.rank_proposals(proposals, "parser_json")
        for rank, (proposal, score) in enumerate(ranked, 1):
            print(f"  {rank}. {proposal.type:15} (score: {score:.3f})")

        print("\n✓ Result: History persisted and reused correctly")


def demo_scenario_5_summary_report():
    """Scenario 5: Summary statistics across all fixtures."""
    print("\n" + "=" * 70)
    print("SCENARIO 5: Summary Report Across All Fixtures")
    print("=" * 70)

    ranker = MemoryDrivenRanker()

    # Build rich history
    print("\n📝 Building history across multiple fixtures:")
    
    fixtures_data = {
        "api_get": [("test_case", True), ("test_case", True), ("instruction", False)],
        "parser_json": [("test_case", True), ("artifact", True), ("instruction", False)],
        "edge_case_1": [("instruction", False), ("instruction", False), ("test_case", True)],
        "cache_hit": [("test_case", True), ("test_case", True), ("test_case", True)],
    }
    
    for fixture_name, outcomes in fixtures_data.items():
        for proposal_type, accepted in outcomes:
            ranker.record_proposal_outcome(fixture_name, proposal_type, accepted=accepted)
        print(f"  ✓ {fixture_name}: {len(outcomes)} proposal outcomes recorded")

    # Generate summary
    print("\n📊 Summary Report:")
    summary = ranker.summary()
    
    print(f"\n  Total Fixtures: {summary['total_fixtures']}")
    print(f"  Average Success Rate: {summary['avg_success_rate']:.0%}")
    print(f"  Tracked Fixtures: {', '.join(summary['fixtures_tracked'])}")
    
    if summary['historically_difficult']:
        print(f"  Difficult Fixtures: {', '.join(summary['historically_difficult'])}")
    
    print("\n  Per-Fixture Details:")
    for name, details in summary['fixture_details'].items():
        print(f"    {name}:")
        print(f"      - Success Rate: {details['success_rate']:.0%} ({details['successful_attempts']}/{details['total_attempts']})")
        print(f"      - Preferred Types: {', '.join(details['preferred_proposal_types'])}")

    print("\n✓ Report generated successfully")


if __name__ == "__main__":
    print("\n" + "🚀 " * 30)
    print("Memory-Driven Proposal Ranking - Interactive Demo".center(90))
    print("🚀 " * 30)

    demo_scenario_1_basic_ranking()
    demo_scenario_2_similarity_borrowing()
    demo_scenario_3_difficult_fixtures()
    demo_scenario_4_persistence()
    demo_scenario_5_summary_report()

    print("\n" + "=" * 70)
    print("✨ All scenarios completed successfully!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1️⃣  Direct success history drives proposal ranking")
    print("  2️⃣  Similar fixtures borrow success patterns")
    print("  3️⃣  Difficult fixtures prioritize reliable proposal types")
    print("  4️⃣  Success records persist across sessions")
    print("  5️⃣  Comprehensive statistics guide operator decisions")
    print()
