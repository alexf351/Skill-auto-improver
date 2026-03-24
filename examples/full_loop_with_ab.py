"""
Example: Full Loop with A/B Evaluation

Demonstrates the complete skill improvement workflow:
1. BASELINE: Evaluate original skill (observe → evaluate)
2. IMPROVE: Generate amendment proposals
3. AMEND: (Hypothetical) Apply amendments
4. VALIDATE: Re-evaluate and compare via A/B
5. DECIDE: Check safety before shipping

This shows how the loop enables autonomous improvement with safety gates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skill_auto_improver.loop import (
    SkillAutoImprover,
    create_golden_evaluator_stage,
    create_amendment_proposal_stage,
    create_ab_evaluation_stage,
)
from skill_auto_improver.evaluator import GoldenFixture


def main():
    print("=" * 80)
    print("FULL WORKFLOW: Baseline → Improve → Validate → A/B Compare → Decide")
    print("=" * 80)
    
    # Define golden test fixtures
    fixtures = [
        GoldenFixture(
            name="greeting_test",
            input_data={"name": "Alice"},
            expected_output={"greeting": "Hello, Alice!"},
        ),
        GoldenFixture(
            name="farewell_test",
            input_data={"name": "Bob"},
            expected_output={"farewell": "Goodbye, Bob!"},
        ),
        GoldenFixture(
            name="numbers_test",
            input_data={"a": 2, "b": 3},
            expected_output={"sum": 5},
        ),
    ]
    
    # Step 1: BASELINE RUN
    print("\n[STEP 1] BASELINE: Evaluate original skill")
    print("-" * 80)
    
    baseline_improver = SkillAutoImprover(
        observe=lambda c: {"signals": ["skill evaluation baseline"]},
        inspect=lambda c: {"patterns": []},
        amend=lambda c: {},  # No amendment yet
        evaluate=create_golden_evaluator_stage(fixtures),
        stage_order=["observe", "inspect", "evaluate"],
    )
    
    baseline_trace = baseline_improver.run_once(
        "/hypothetical/skill",
        logs_dir="./runs"
    )
    
    baseline_eval = None
    for step in baseline_trace.steps:
        if step.name == "evaluate":
            baseline_eval = step.output
            print(f"  Pass rate: {step.output.get('pass_rate', 0):.1%}")
            print(f"  Passed: {step.output.get('passed')}/{step.output.get('total')}")
    
    # Step 2: GENERATE PROPOSALS
    print("\n[STEP 2] IMPROVE: Generate amendment proposals")
    print("-" * 80)
    
    proposal_improver = SkillAutoImprover(
        observe=lambda c: {"signals": ["analyzing failures"]},
        inspect=lambda c: {"patterns": ["greeting mismatch", "farewell mismatch"]},
        evaluate=create_golden_evaluator_stage(fixtures),
        amend=create_amendment_proposal_stage(),
        stage_order=["observe", "inspect", "evaluate", "amend"],
    )
    
    proposal_trace = proposal_improver.run_once(
        "/hypothetical/skill",
        logs_dir="./runs"
    )
    
    proposals = None
    for step in proposal_trace.steps:
        if step.name == "amend":
            proposals = step.output.get("proposals", [])
            print(f"  Generated {len(proposals)} proposals:")
            for p in proposals:
                print(f"    • {p['type']}: {p['description']} (confidence: {p['confidence']})")
    
    # Step 3: AMEND (Hypothetical)
    print("\n[STEP 3] AMEND: Apply accepted proposals (hypothetical)")
    print("-" * 80)
    print("  [In real workflow: user reviews proposals, accepts/rejects, applies to skill]")
    print("  Scenario: User accepts all proposals")
    
    # Step 4: VALIDATE - Re-evaluate amended skill
    print("\n[STEP 4] VALIDATE: Re-evaluate amended skill")
    print("-" * 80)
    
    # Simulate improved skill (all tests now pass)
    # In reality, evaluator would re-run against the actual amended skill
    after_eval_output = {
        "total": 3,
        "passed": 3,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [
            {
                "fixture_name": "greeting_test",
                "passed": True,
                "expected": {"greeting": "Hello, Alice!"},
                "actual": {"greeting": "Hello, Alice!"},
                "delta": {},
                "reason": "",
            },
            {
                "fixture_name": "farewell_test",
                "passed": True,
                "expected": {"farewell": "Goodbye, Bob!"},
                "actual": {"farewell": "Goodbye, Bob!"},
                "delta": {},
                "reason": "",
            },
            {
                "fixture_name": "numbers_test",
                "passed": True,
                "expected": {"sum": 5},
                "actual": {"sum": 5},
                "delta": {},
                "reason": "",
            },
        ],
    }
    
    print(f"  Pass rate: {after_eval_output['pass_rate']:.1%}")
    print(f"  Passed: {after_eval_output['passed']}/{after_eval_output['total']}")
    
    # Step 5: A/B COMPARE
    print("\n[STEP 5] A/B COMPARE: Regression detection + improvement metrics")
    print("-" * 80)
    
    # Create a dummy context with before/after evaluations
    ab_context = {
        "before_eval": baseline_eval,
        "after_eval": after_eval_output,
    }
    
    ab_stage = create_ab_evaluation_stage()
    ab_output = ab_stage(ab_context)
    
    print(f"  Before pass rate:    {ab_output['before_pass_rate']:.1%}")
    print(f"  After pass rate:     {ab_output['after_pass_rate']:.1%}")
    print(f"  Improvement:         +{ab_output['pass_rate_delta']:.1%}")
    print(f"  Recovered tests:     {ab_output['recovered_count']}")
    print(f"  Regressions:         {ab_output['regressed_count']}")
    print(f"  Safety:              {'✓ SAFE' if ab_output['is_safe'] else '✗ UNSAFE'}")
    
    # Step 6: DECISION
    print("\n[STEP 6] DECISION: Ship or rollback?")
    print("-" * 80)
    
    if ab_output['is_safe'] and ab_output['pass_rate_delta'] > 0:
        print("  ✅ RECOMMENDATION: SHIP")
        print(f"  Reason: No regressions + positive improvement ({ab_output['pass_rate_delta']:.1%})")
    elif not ab_output['is_safe']:
        print("  ❌ RECOMMENDATION: ROLLBACK")
        print(f"  Reason: {ab_output['regressed_count']} regression(s) detected")
    else:
        print("  ⏸️ RECOMMENDATION: REVIEW")
        print("  Reason: Safety OK but no net improvement")
    
    print("\n" + "=" * 80)
    print("Workflow complete! This loop can be triggered autonomously or on-demand.")
    print("=" * 80)


if __name__ == "__main__":
    main()
