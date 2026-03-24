#!/usr/bin/env python3
"""
Full Loop Example: Observe → Inspect → Evaluate → Amend

Demonstrates the complete skill auto-improver pipeline:
1. Observe: Gather logs/signals (simulated)
2. Inspect: Analyze failure patterns (simulated)
3. Evaluate: Score against golden fixtures
4. Amend: Generate patch proposals from failures

This is the core improvement loop: failing tests → proposals → skill updates.
"""

import sys
sys.path.insert(0, 'src')

from skill_auto_improver.loop import (
    SkillAutoImprover,
    create_golden_evaluator_stage,
    create_amendment_proposal_stage,
)
from skill_auto_improver.evaluator import GoldenFixture
import json


def simulate_skill_run(context: dict) -> dict:
    """Simulate running a real skill and capturing output."""
    # In a real system, this would:
    # 1. Load the skill
    # 2. Execute it with test inputs
    # 3. Capture outputs
    return {
        "signals": ["test_greeting failed", "test_math succeeded"],
        "actual_outputs": {
            "greeting_test": {"greeting": "Hi, Alice"},  # WRONG: should be "Hello, Alice!"
            "math_test": {"sum": 5},  # INCOMPLETE: missing "product"
        },
    }


def inspect_failures(context: dict) -> dict:
    """Analyze signals to identify failure patterns."""
    signals = context.get("observe", {}).get("signals", [])
    
    issues = []
    for signal in signals:
        if "failed" in signal:
            issues.append(f"Pattern detected: {signal}")
    
    return {
        "failure_patterns": issues,
        "recommendation": "Run golden evaluator to quantify impact",
    }


def main():
    print("=" * 70)
    print("SKILL AUTO-IMPROVER: FULL LOOP WITH PROPOSALS")
    print("=" * 70)
    print()

    # Define golden test fixtures
    fixtures = [
        GoldenFixture(
            name="greeting_test",
            input_data={"name": "Alice"},
            expected_output={"greeting": "Hello, Alice!"},
            tags=["greeting", "core"],
        ),
        GoldenFixture(
            name="math_test",
            input_data={"a": 2, "b": 3},
            expected_output={"sum": 5, "product": 6},
            tags=["math", "core"],
        ),
    ]

    print(f"Loaded {len(fixtures)} golden fixtures")
    for f in fixtures:
        print(f"  - {f.name}: {f.expected_output}")
    print()

    # Create pipeline stages
    # Note: The pipeline order is observe → inspect → amend → evaluate
    # So amend runs BEFORE evaluate. For this example, we swap to show proposals.
    # In production, you'd run evaluate first, then amend in a second pass.
    observe = simulate_skill_run
    inspect = inspect_failures
    evaluate = create_golden_evaluator_stage(fixtures)
    amend = create_amendment_proposal_stage()

    # Run the pipeline with custom order: evaluate BEFORE amend so proposals see test results
    improver = SkillAutoImprover(
        observe=observe,
        inspect=inspect,
        amend=amend,
        evaluate=evaluate,
        stage_order=["observe", "inspect", "evaluate", "amend"],  # Custom order
    )

    print("Running observe → inspect → evaluate → amend pipeline...")
    print()

    trace = improver.run_once(
        skill_path="/example/skill",
        logs_dir="/tmp/skill_runs",
    )

    # Print results
    print(f"Pipeline status: {trace.status}")
    print(f"Run ID: {trace.run_id}")
    print()

    # Show each stage's output
    for step in trace.steps:
        print(f"--- {step.name.upper()} ---")
        if step.output:
            print(json.dumps(step.output, indent=2))
        print()

    # Extract and display evaluation results
    print("=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)
    for step in trace.steps:
        if step.name == "evaluate":
            eval_output = step.output
            print(f"Total tests: {eval_output.get('total', 0)}")
            print(f"Passed: {eval_output.get('passed', 0)}")
            print(f"Failed: {eval_output.get('failed', 0)}")
            print(f"Pass rate: {eval_output.get('pass_rate', 0):.0%}")
            print()

            if eval_output.get("results"):
                print("Test Results:")
                for result in eval_output["results"]:
                    status = "✓ PASS" if result["passed"] else "✗ FAIL"
                    print(f"  {status}: {result['fixture_name']}")
                    if result.get("delta"):
                        for key, delta in result["delta"].items():
                            print(f"    {key}: {delta['expected']} → {delta['actual']}")
                print()

    # Extract and display amendment proposals
    print("=" * 70)
    print("AMENDMENT PROPOSALS")
    print("=" * 70)
    for step in trace.steps:
        if step.name == "amend":
            proposals_output = step.output
            total_proposals = proposals_output.get("total_proposals", 0)
            total_failures = proposals_output.get("total_failures", 0)
            
            print(f"Failures detected: {total_failures}")
            print(f"Proposals generated: {total_proposals}")
            print()

            if proposals_output.get("proposals"):
                # Group by type
                by_type = {}
                for prop in proposals_output["proposals"]:
                    ptype = prop["type"]
                    if ptype not in by_type:
                        by_type[ptype] = []
                    by_type[ptype].append(prop)

                for ptype, proposals in by_type.items():
                    print(f"\n{ptype.upper()} PROPOSALS ({len(proposals)}):")
                    for prop in proposals:
                        print(f"  [{prop['severity']}] {prop['fixture_name']}")
                        print(f"    {prop['description']}")
                        print(f"    Confidence: {prop['confidence']:.0%}")
                print()

    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("""
To use these proposals:
1. Review instruction proposals → update SKILL.md if needed
2. Review test case proposals → add to golden fixtures to prevent regression
3. Use reasoning proposals for debugging (root cause analysis)
4. Run the loop again to verify improvements

The cycle repeats: observe → inspect → evaluate → amend → update → evaluate again.
""")


if __name__ == "__main__":
    main()
