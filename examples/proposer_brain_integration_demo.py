#!/usr/bin/env python3
"""
Demo: Proposer + SharedBrain Integration

Shows how the proposal engine now leverages cross-skill learning from the shared brain.
Demonstrates:
1. Creating proposals without brain (baseline)
2. Creating proposals with brain context
3. Comparing confidence scores and hints
4. Observing cross-skill learning in action
"""

import tempfile
from pathlib import Path

from skill_auto_improver.proposer import ProposalEngine
from skill_auto_improver.shared_brain import SharedBrain, PromotionWisdom, RegressionPattern, CoreDirective
from skill_auto_improver.evaluator import TestResult


def demo_proposer_without_brain():
    """Baseline: proposals without brain context."""
    print("=" * 70)
    print("1. BASELINE: Proposals without Brain Context")
    print("=" * 70)
    
    engine = ProposalEngine()  # No brain
    
    failed_result = TestResult(
        fixture_name="greeting_format",
        passed=False,
        expected={"greeting": "Hello, World!", "formal": True},
        actual={"greeting": "Hi", "formal": False},
        delta={
            "greeting": "Expected 'Hello, World!' but got 'Hi'",
            "formal": "Expected True but got False",
        },
    )
    
    report = engine.generate_proposals([failed_result])
    
    print(f"Total failures: {report.total_failures}")
    print(f"Total proposals: {report.total_proposals}")
    print(f"Brain context available: {report.memory_context.get('brain_context', False)}\n")
    
    for i, proposal in enumerate(report.proposals, 1):
        print(f"Proposal {i}: {proposal.type}")
        print(f"  Confidence: {proposal.confidence:.2f}")
        print(f"  Severity: {proposal.severity}")
        print(f"  Description: {proposal.description[:80]}...\n")
    
    return report


def demo_proposer_with_brain():
    """Enhanced: proposals with brain context."""
    print("=" * 70)
    print("2. ENHANCED: Proposals with Brain Context")
    print("=" * 70)
    
    # Create shared brain
    temp_dir = tempfile.TemporaryDirectory()
    brain_dir = Path(temp_dir.name)
    brain = SharedBrain(brain_dir)
    
    # Populate brain with promotion wisdom for this fixture
    wisdom = PromotionWisdom(
        id="pw_demo_001",
        fixture_name="greeting_format",
        description="Formal greeting with test cases pattern",
        acceptance_reason="100% recovery across multiple skills when test cases added first",
        skills_successful=["kiro-ugc-brief", "morning-brief", "weather-brief"],
        proposal_type_sequence=["test_case", "instruction"],
        confidence_floor=0.85,
        confidence=0.92,
        shared_lessons=[
            "Test cases MUST come before instruction edits for formal greeting",
            "Backward compatibility critical - test old format too",
            "Check timezone/locale impact on greeting output",
        ],
        promotion_count=7,
    )
    brain.promotion_wisdom[wisdom.id] = wisdom
    
    # Add regression pattern
    pattern = RegressionPattern(
        id="rp_demo_001",
        pattern_name="instruction_without_test",
        description="Instruction-only changes to greeting often miss edge cases",
        triggers=["instruction_proposal_without_test_case"],
        fix_strategy="Always require test case proposals first for greeting logic",
        severity="critical",
        observed_in_skills=["kiro-dev-assistant", "kiro-content-calendar"],
        prevention_rule="require_test_case_for_protected_fixtures",
        occurrence_count=4,
        prevention_success_rate=0.95,
    )
    brain.regression_patterns[pattern.id] = pattern
    
    # Add core directive
    directive = CoreDirective(
        id="cd_demo_001",
        title="min_confidence_greeting",
        description="Greeting changes need high confidence (0.85+)",
        applies_to=["*"],
        auto_apply=True,
        example="greeting_format and formal_greeting fixtures",
    )
    brain.core_directives[directive.id] = directive
    
    # Create engine with brain
    engine = ProposalEngine(brain=brain)
    
    failed_result = TestResult(
        fixture_name="greeting_format",
        passed=False,
        expected={"greeting": "Hello, World!", "formal": True},
        actual={"greeting": "Hi", "formal": False},
        delta={
            "greeting": "Expected 'Hello, World!' but got 'Hi'",
            "formal": "Expected True but got False",
        },
    )
    
    # Generate proposals WITH brain context
    report = engine.generate_proposals(
        [failed_result],
        skill_name="test-skill",
        skill_path=Path("/tmp/test-skill"),
    )
    
    print(f"Total failures: {report.total_failures}")
    print(f"Total proposals: {report.total_proposals}")
    print(f"Brain context available: {report.memory_context.get('brain_context', False)}\n")
    
    # Show brain context loaded
    if report.memory_context.get("brain_context"):
        print("Brain Context Loaded:")
        if report.memory_context.get("skill_mastery"):
            mastery = report.memory_context["skill_mastery"]
            print(f"  Skill Mastery:")
            print(f"    - Trial Count: {mastery.get('trial_count')}")
            print(f"    - Success Rate: {mastery.get('success_rate'):.1%}")
            print(f"    - Most Useful Type: {mastery.get('most_useful_proposal_type')}")
        if report.memory_context.get("core_directives"):
            print(f"  Core Directives: {len(report.memory_context['core_directives'])} loaded")
        if report.memory_context.get("regression_patterns"):
            print(f"  Regression Patterns: {len(report.memory_context['regression_patterns'])} patterns")
        print()
    
    for i, proposal in enumerate(report.proposals, 1):
        print(f"Proposal {i}: {proposal.type}")
        print(f"  Confidence: {proposal.confidence:.2f}")
        print(f"  Severity: {proposal.severity}")
        print(f"  Description: {proposal.description[:80]}...\n")
    
    temp_dir.cleanup()
    return report


def compare_results():
    """Compare results from both runs."""
    print("=" * 70)
    print("3. COMPARISON: Without Brain vs With Brain")
    print("=" * 70)
    
    report_baseline = demo_proposer_without_brain()
    print()
    report_enhanced = demo_proposer_with_brain()
    
    print("\n" + "=" * 70)
    print("KEY OBSERVATIONS:")
    print("=" * 70)
    
    # Find test_case proposals in each
    baseline_test_proposals = [p for p in report_baseline.proposals if p.type == "test_case"]
    enhanced_test_proposals = [p for p in report_enhanced.proposals if p.type == "test_case"]
    
    if baseline_test_proposals and enhanced_test_proposals:
        baseline_conf = baseline_test_proposals[0].confidence
        enhanced_conf = enhanced_test_proposals[0].confidence
        boost = enhanced_conf - baseline_conf
        
        print(f"\nTest Case Proposal Confidence:")
        print(f"  Baseline (no brain):     {baseline_conf:.2f}")
        print(f"  With brain context:      {enhanced_conf:.2f}")
        print(f"  Boost from brain wisdom: +{boost:.2f} (+{boost/baseline_conf*100:.0f}%)")
    
    print(f"\nProposal Ordering:")
    print(f"  Baseline types:     {[p.type for p in report_baseline.proposals[:3]]}")
    print(f"  Enhanced types:     {[p.type for p in report_enhanced.proposals[:3]]}")
    print(f"  Note: Brain context may reorder based on learned success patterns")
    
    print(f"\nMemory Context:")
    print(f"  Baseline brain context:  {report_baseline.memory_context.get('brain_context', False)}")
    print(f"  Enhanced brain context:  {report_enhanced.memory_context.get('brain_context', False)}")
    
    print("\n✓ Brain integration increases proposal confidence and applies cross-skill learning")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PROPOSER + SHAREDBRAIN INTEGRATION DEMO")
    print("=" * 70)
    print("\nThis demo shows how the proposal engine now leverages cross-skill")
    print("learning from the shared brain to generate smarter proposals.\n")
    
    compare_results()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("\nKey takeaways:")
    print("1. ProposalEngine accepts optional SharedBrain (backward compatible)")
    print("2. Brain context loads promotion wisdom, patterns, and directives")
    print("3. Confidence scores boosted by promotion wisdom")
    print("4. Proposal ranking considers what's worked in other skills")
    print("5. Cross-skill lessons enriched into memory hints")
    print("\n")
