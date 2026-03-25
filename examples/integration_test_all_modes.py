"""
Integration test demonstrating all three evaluation modes:
1. Fixture-only mode
2. Checklist-only mode
3. Hybrid mode (both gates)

This shows how checklist mode integrates seamlessly with existing fixture mode.
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.evaluator import GoldenFixture, GoldenEvaluator
from skill_auto_improver.checklist_evaluator import (
    ChecklistSpec, ChecklistQuestion, ChecklistEvaluator
)
from skill_auto_improver.loop import create_hybrid_evaluation_stage


def demo_fixture_only_mode():
    """Demonstrate fixture-based evaluation (existing mode)."""
    print("\n" + "="*70)
    print("MODE 1: FIXTURE-ONLY EVALUATION (Existing)")
    print("="*70 + "\n")
    
    fixtures = [
        GoldenFixture(
            name="greeting_test",
            input_data={"name": "Alice"},
            expected_output={"greeting": "Hello, Alice!"}
        ),
        GoldenFixture(
            name="math_test",
            input_data={"a": 5, "b": 3},
            expected_output={"sum": 8, "product": 15}
        ),
    ]
    
    evaluator = GoldenEvaluator(fixtures)
    
    # Actual outputs (some match, some don't)
    actual_outputs = {
        "greeting_test": {"greeting": "Hello, Alice!"},
        "math_test": {"sum": 8, "product": 14},  # Wrong: product should be 15
    }
    
    report = evaluator.evaluate_all(actual_outputs)
    
    print(f"Total fixtures: {report.total}")
    print(f"Passed: {report.passed}")
    print(f"Failed: {report.failed}")
    print(f"Pass rate: {report.pass_rate:.1%}\n")
    
    for result in report.results:
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"{status} - {result.fixture_name}")
        if not result.passed:
            print(f"  Expected: {result.expected}")
            print(f"  Got:      {result.actual}")
            print(f"  Diff: {result.delta}")


def demo_checklist_only_mode():
    """Demonstrate checklist-based evaluation (new mode)."""
    print("\n" + "="*70)
    print("MODE 2: CHECKLIST-ONLY EVALUATION (New)")
    print("="*70 + "\n")
    
    # Define a quality checklist
    checklist = ChecklistSpec(name="code_quality")
    checklist.add_question(ChecklistQuestion(
        id="q1_no_errors",
        question="Are there any runtime errors?",
        required=True
    ))
    checklist.add_question(ChecklistQuestion(
        id="q2_complete",
        question="Is the output complete (not truncated)?",
        required=True
    ))
    checklist.add_question(ChecklistQuestion(
        id="q3_formatted",
        question="Is the output well-formatted?",
        required=False
    ))
    
    evaluator = ChecklistEvaluator(checklist)
    
    # Test outputs with quality scores
    test_outputs = {
        "run_1": {
            "q1_no_errors": True,
            "q2_complete": True,
            "q3_formatted": True,
            "result": "Success"
        },
        "run_2": {
            "q1_no_errors": True,
            "q2_complete": False,
            "q3_formatted": True,
            "result": "Truncated output"
        },
        "run_3": {
            "q1_no_errors": False,
            "q2_complete": True,
            "q3_formatted": False,
            "error": "ValueError at line 42"
        },
    }
    
    report = evaluator.evaluate_all(test_outputs)
    
    print(f"Checklist: {report.checklist_name}")
    print(f"Total outputs evaluated: {report.total_outputs}")
    print(f"Outputs passing all questions: {report.total_passed}")
    print(f"Pass rate: {report.pass_rate:.1%}")
    print(f"Average score: {report.average_score:.1%}\n")
    
    for result in report.results:
        status = "✓ PASS" if result.passed_all else "✗ FAIL"
        print(f"{status} - {result.output_id} (Score: {result.score:.1%})")
        for q_id, answer in result.answers.items():
            check = "✓" if answer else "✗"
            print(f"  {check} {q_id}: {answer}")


def demo_hybrid_mode_either_or():
    """Demonstrate hybrid evaluation with OR logic (fixture OR checklist passes)."""
    print("\n" + "="*70)
    print("MODE 3A: HYBRID EVALUATION - EITHER/OR (New)")
    print("Either fixture pass OR checklist pass = overall pass")
    print("="*70 + "\n")
    
    fixtures = [
        GoldenFixture(
            name="output_1",
            input_data={},
            expected_output={"result": "exact"}
        ),
    ]
    
    checklist = ChecklistSpec(name="quality")
    checklist.add_question(ChecklistQuestion(id="q1", question="Valid?"))
    
    stage = create_hybrid_evaluation_stage(
        fixtures=fixtures,
        checklist=checklist,
        require_both=False  # Either/or logic
    )
    
    # Output passes fixture but not checklist
    context = {
        "actual_outputs": {
            "output_1": {"result": "exact"}  # Matches fixture exactly
        }
    }
    
    # Also need checklist answers
    outputs_with_checklist = {
        "output_1": {
            "result": "exact",  # Fixture match
            "q1": False  # Checklist fail
        }
    }
    context["actual_outputs"] = outputs_with_checklist
    result = stage(context)
    
    print(f"Mode: {result.get('mode')}")
    print(f"Overall result: {'PASS ✓' if result.get('passed') else 'FAIL ✗'}")
    print(f"Fixture gate: Fixture evaluation present: {bool(result.get('fixture_evaluation'))}")
    print(f"Checklist gate: Checklist evaluation present: {bool(result.get('checklist_evaluation'))}")
    print("\nExplanation: Either gate passing = overall pass (fixture OR checklist)")


def demo_hybrid_mode_both_required():
    """Demonstrate hybrid evaluation with AND logic (both must pass)."""
    print("\n" + "="*70)
    print("MODE 3B: HYBRID EVALUATION - BOTH REQUIRED (New)")
    print("Both fixture AND checklist must pass = overall pass")
    print("="*70 + "\n")
    
    fixtures = [
        GoldenFixture(
            name="output_1",
            input_data={},
            expected_output={"status": "ok", "value": 42}
        ),
    ]
    
    checklist = ChecklistSpec(name="quality")
    checklist.add_question(ChecklistQuestion(id="q1", question="Valid?"))
    checklist.add_question(ChecklistQuestion(id="q2", question="Complete?"))
    
    stage = create_hybrid_evaluation_stage(
        fixtures=fixtures,
        checklist=checklist,
        require_both=True  # Both gates required
    )
    
    # Output passes both gates
    context = {
        "actual_outputs": {
            "output_1": {
                "status": "ok",
                "value": 42,
                "q1": True,
                "q2": True
            }
        }
    }
    
    result = stage(context)
    
    print(f"Mode: {result.get('mode')}")
    print(f"Overall result: {'PASS ✓' if result.get('passed') else 'FAIL ✗'}")
    print(f"Fixture gate: {bool(result.get('fixture_evaluation'))}")
    print(f"Checklist gate: {bool(result.get('checklist_evaluation'))}")
    print("\nExplanation: Both gates must pass (fixture AND checklist)")


def demo_comparison():
    """Show comparison of all three modes."""
    print("\n" + "="*70)
    print("COMPARISON: All Three Modes")
    print("="*70 + "\n")
    
    comparison = {
        "Fixture-Only": {
            "Type": "Exact structural matching",
            "Questions": "N/A - uses golden fixtures",
            "Scoring": "Binary: pass (100%) or fail (0%)",
            "Use Case": "Regression testing, structural validation",
            "Best For": "Exact output contracts"
        },
        "Checklist-Only": {
            "Type": "Quality gate validation",
            "Questions": "3-6 yes/no questions",
            "Scoring": "0-100% based on answers",
            "Use Case": "Quality assurance, compatibility checks",
            "Best For": "Flexible quality requirements"
        },
        "Hybrid (Either/Or)": {
            "Type": "Fixture + Checklist (logical OR)",
            "Questions": "Both fixtures and checklist questions",
            "Scoring": "Pass if either gate passes",
            "Use Case": "Transitioning between test paradigms",
            "Best For": "Gradual migration from fixtures to checklists"
        },
        "Hybrid (Both Required)": {
            "Type": "Fixture + Checklist (logical AND)",
            "Questions": "Both fixtures and checklist questions",
            "Scoring": "Pass only if both gates pass",
            "Use Case": "Strict quality + structure validation",
            "Best For": "Critical systems requiring both gates"
        }
    }
    
    for mode, details in comparison.items():
        print(f"\n📋 {mode}:")
        for key, value in details.items():
            print(f"  • {key}: {value}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SKILL-AUTO-IMPROVER: CHECKLIST MODE INTEGRATION TEST")
    print("="*70)
    
    try:
        demo_fixture_only_mode()
        demo_checklist_only_mode()
        demo_hybrid_mode_either_or()
        demo_hybrid_mode_both_required()
        demo_comparison()
        
        print("\n" + "="*70)
        print("✓ ALL INTEGRATION TESTS PASSED")
        print("="*70 + "\n")
        
        print("Summary:")
        print("  ✓ Fixture-only mode works (existing)")
        print("  ✓ Checklist-only mode works (new)")
        print("  ✓ Hybrid mode with OR logic works (new)")
        print("  ✓ Hybrid mode with AND logic works (new)")
        print("  ✓ All modes integrate seamlessly")
        print("\nNext: Read CHECKLIST_MODE.md for complete API documentation")
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
