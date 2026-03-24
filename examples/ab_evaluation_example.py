"""
Example: A/B Evaluation with Regression Detection

Demonstrates how to use the A/B evaluator to:
1. Capture baseline skill performance (before)
2. Run amendment (improvement)
3. Compare after evaluation against before
4. Detect regressions automatically
"""
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skill_auto_improver.ab_evaluator import ABEvaluator
from skill_auto_improver.evaluator import EvaluationReport, TestResult


def example_ab_full_flow():
    """
    Full workflow: baseline run → amendment → A/B comparison with regression detection.
    """
    print("=" * 70)
    print("A/B Evaluation Example: Detect Improvements & Regressions")
    print("=" * 70)
    
    # Step 1: Capture BEFORE evaluation (original skill)
    print("\n[1] BASELINE: Evaluate original skill")
    print("-" * 70)
    
    before_results = [
        TestResult("test_greeting", False, {"greeting": "Hello, Alice!"}, {"greeting": "Hi, Alice"}),
        TestResult("test_farewell", False, {"farewell": "Goodbye, Bob!"}, {"farewell": "Bye, Bob"}),
        TestResult("test_numbers", True, {"sum": 5}, {"sum": 5}),
    ]
    before_report = EvaluationReport(
        total=3,
        passed=1,
        failed=2,
        results=before_results,
    )
    
    print(f"  Pass rate: {before_report.pass_rate:.1%} ({before_report.passed}/{before_report.total})")
    print(f"  Failures:")
    for r in before_results:
        if not r.passed:
            print(f"    - {r.fixture_name}: expected {r.expected}, got {r.actual}")
    
    # Step 2: (Hypothetical) Amendment applied to skill
    # In real flow: run propose → user reviews → apply amendment
    print("\n[2] AMENDMENT: Improvement proposal applied to skill")
    print("-" * 70)
    print("  • Updated greeting instruction in SKILL.md")
    print("  • Added regression test for farewell edge case")
    
    # Step 3: Evaluate AFTER amendment
    print("\n[3] AFTER: Re-evaluate amended skill")
    print("-" * 70)
    
    after_results = [
        TestResult("test_greeting", True, {"greeting": "Hello, Alice!"}, {"greeting": "Hello, Alice!"}),
        TestResult("test_farewell", True, {"farewell": "Goodbye, Bob!"}, {"farewell": "Goodbye, Bob!"}),
        TestResult("test_numbers", True, {"sum": 5}, {"sum": 5}),
    ]
    after_report = EvaluationReport(
        total=3,
        passed=3,
        failed=0,
        results=after_results,
    )
    
    print(f"  Pass rate: {after_report.pass_rate:.1%} ({after_report.passed}/{after_report.total})")
    print(f"  All tests passing ✓")
    
    # Step 4: A/B comparison
    print("\n[4] A/B COMPARISON: Regression Detection & Improvement Metrics")
    print("-" * 70)
    
    ab_evaluator = ABEvaluator()
    ab_report = ab_evaluator.compare(before_report, after_report)
    
    print(f"  Before:              {ab_report.before_pass_rate:.1%} ({ab_report.before_passed}/{ab_report.before_total})")
    print(f"  After:               {ab_report.after_pass_rate:.1%} ({ab_report.after_passed}/{ab_report.after_total})")
    print(f"  Improvement:         +{ab_report.pass_rate_delta:.1%}")
    print(f"\n  Recovery metrics:")
    print(f"    • Recovered:       {ab_report.recovered_count} test(s)")
    print(f"    • Regressions:     {ab_report.regressed_count} test(s)")
    print(f"    • Stable passes:   {ab_report.stable_pass_count} test(s)")
    print(f"    • Stable fails:    {ab_report.stable_fail_count} test(s)")
    print(f"\n  Safety check: {'✓ SAFE (no regressions)' if ab_report.is_safe else '✗ UNSAFE (regressions detected)'}")
    
    print(f"\n  Detailed comparison:")
    for comp in ab_report.comparisons:
        status_icon = "✓" if comp.status in ["stable_pass", "recovered"] else "✗"
        print(f"    {status_icon} {comp.fixture_name}: {comp.status}")
        if comp.status == "recovered":
            print(f"       Before: {comp.before_actual} → After: {comp.after_actual}")
    
    # Serialize to dict for API/storage
    print(f"\n[5] SERIALIZATION: Export to JSON/API")
    print("-" * 70)
    ab_dict = ab_report.to_dict()
    print(f"  Keys in report: {list(ab_dict.keys())}")
    print(f"  Example: pass_rate_delta={ab_dict['pass_rate_delta']}, is_safe={ab_dict['is_safe']}")
    

def example_ab_with_regressions():
    """
    Scenario: Improvement that introduces a regression.
    Illustrates safety detection.
    """
    print("\n\n" + "=" * 70)
    print("A/B Evaluation Example: Detecting Regressions")
    print("=" * 70)
    
    print("\n[BEFORE] Original skill")
    print("-" * 70)
    before_results = [
        TestResult("test_api_call", True, {"status": 200}, {"status": 200}),
        TestResult("test_retry_logic", False, {"retries": 3}, {"retries": 5}),
    ]
    before_report = EvaluationReport(total=2, passed=1, failed=1, results=before_results)
    print(f"  Pass rate: {before_report.pass_rate:.1%}")
    
    print("\n[AFTER] Amended skill (with regression)")
    print("-" * 70)
    after_results = [
        TestResult("test_api_call", False, {"status": 200}, {"status": 500}),  # REGRESSION!
        TestResult("test_retry_logic", True, {"retries": 3}, {"retries": 3}),
    ]
    after_report = EvaluationReport(total=2, passed=1, failed=1, results=after_results)
    print(f"  Pass rate: {after_report.pass_rate:.1%}")
    
    print("\n[A/B] Comparison")
    print("-" * 70)
    ab_evaluator = ABEvaluator()
    ab_report = ab_evaluator.compare(before_report, after_report)
    
    print(f"  Recovered:     {ab_report.recovered_count}")
    print(f"  Regressions:   {ab_report.regressed_count} ⚠️")
    print(f"  Is safe:       {ab_report.is_safe} ❌")
    
    print(f"\n  Details:")
    for comp in ab_report.comparisons:
        if comp.status == "regressed":
            print(f"    ⚠️ REGRESSION: {comp.fixture_name}")
            print(f"       Was passing before, now failing")
            print(f"       Expected: {comp.before_actual} → Got: {comp.after_actual}")


def example_ab_mixed_outcomes():
    """
    Scenario: Improvement that recovers some tests but adds new ones.
    """
    print("\n\n" + "=" * 70)
    print("A/B Evaluation Example: Mixed Outcomes (Recovery + New Tests)")
    print("=" * 70)
    
    print("\n[BEFORE] Original skill (3 tests)")
    print("-" * 70)
    before_report = EvaluationReport(
        total=3,
        passed=1,
        failed=2,
        results=[
            TestResult("test_basic", True, {"ok": True}, {"ok": True}),
            TestResult("test_edge_case_1", False, {"x": 1}, {"x": 0}),
            TestResult("test_edge_case_2", False, {"y": 2}, {"y": 0}),
        ],
    )
    print(f"  Pass rate: {before_report.pass_rate:.1%}")
    
    print("\n[AFTER] Amended skill (5 tests, includes 2 new)")
    print("-" * 70)
    after_report = EvaluationReport(
        total=5,
        passed=4,
        failed=1,
        results=[
            TestResult("test_basic", True, {"ok": True}, {"ok": True}),
            TestResult("test_edge_case_1", True, {"x": 1}, {"x": 1}),  # Recovered
            TestResult("test_edge_case_2", False, {"y": 2}, {"y": 0}),  # Still failing
            TestResult("test_new_1", True, {"z": 3}, {"z": 3}),         # New pass
            TestResult("test_new_2", True, {"w": 4}, {"w": 4}),         # New pass
        ],
    )
    print(f"  Pass rate: {after_report.pass_rate:.1%}")
    
    print("\n[A/B] Analysis")
    print("-" * 70)
    ab_evaluator = ABEvaluator()
    ab_report = ab_evaluator.compare(before_report, after_report)
    
    print(f"  Before:        {ab_report.before_pass_rate:.1%}")
    print(f"  After:         {ab_report.after_pass_rate:.1%}")
    print(f"  Net gain:      +{ab_report.pass_rate_delta:.1%}")
    print(f"  Recovered:     {ab_report.recovered_count}")
    print(f"  Regressions:   {ab_report.regressed_count}")
    print(f"  Safe:          {ab_report.is_safe}")
    print(f"\n  Summary: Good improvement (recovered test_edge_case_1) + new passing tests")
    print(f"           No regressions ✓")


if __name__ == "__main__":
    example_ab_full_flow()
    example_ab_with_regressions()
    example_ab_mixed_outcomes()
    
    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
