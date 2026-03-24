"""Tests for A/B evaluation runner."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.ab_evaluator import ABEvaluator, ABReport
from skill_auto_improver.evaluator import EvaluationReport, TestResult


class ABEvaluatorTests(unittest.TestCase):
    """Test A/B evaluation and regression detection."""
    
    def setUp(self):
        self.evaluator = ABEvaluator()
    
    def test_compare_all_recovered(self):
        """All tests recovered (fail → pass)."""
        before = EvaluationReport(total=2, passed=0, failed=2, results=[
            TestResult("test1", False, {"x": 1}, {"x": 0}),
            TestResult("test2", False, {"y": 2}, {"y": 1}),
        ])
        after = EvaluationReport(total=2, passed=2, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
            TestResult("test2", True, {"y": 2}, {"y": 2}),
        ])
        
        ab = self.evaluator.compare(before, after)
        
        self.assertEqual(ab.before_pass_rate, 0.0)
        self.assertEqual(ab.after_pass_rate, 1.0)
        self.assertEqual(ab.pass_rate_delta, 1.0)
        self.assertEqual(ab.recovered_count, 2)
        self.assertEqual(ab.regressed_count, 0)
        self.assertTrue(ab.is_safe)
    
    def test_compare_no_regressions(self):
        """Improved without breaking existing passes."""
        before = EvaluationReport(total=3, passed=1, failed=2, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
            TestResult("test2", False, {"y": 2}, {"y": 1}),
            TestResult("test3", False, {"z": 3}, {"z": 0}),
        ])
        after = EvaluationReport(total=3, passed=3, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
            TestResult("test2", True, {"y": 2}, {"y": 2}),
            TestResult("test3", True, {"z": 3}, {"z": 3}),
        ])
        
        ab = self.evaluator.compare(before, after)
        
        self.assertEqual(ab.before_pass_rate, 1/3)
        self.assertEqual(ab.after_pass_rate, 1.0)
        self.assertAlmostEqual(ab.pass_rate_delta, 2/3, places=5)
        self.assertEqual(ab.recovered_count, 2)
        self.assertEqual(ab.regressed_count, 0)
        self.assertEqual(ab.stable_pass_count, 1)
        self.assertTrue(ab.is_safe)
    
    def test_compare_with_regressions(self):
        """Detects regressions (pass → fail)."""
        before = EvaluationReport(total=2, passed=2, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
            TestResult("test2", True, {"y": 2}, {"y": 2}),
        ])
        after = EvaluationReport(total=2, passed=1, failed=1, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
            TestResult("test2", False, {"y": 2}, {"y": 1}),
        ])
        
        ab = self.evaluator.compare(before, after)
        
        self.assertEqual(ab.before_pass_rate, 1.0)
        self.assertEqual(ab.after_pass_rate, 0.5)
        self.assertEqual(ab.pass_rate_delta, -0.5)
        self.assertEqual(ab.recovered_count, 0)
        self.assertEqual(ab.regressed_count, 1)
        self.assertEqual(ab.stable_pass_count, 1)
        self.assertFalse(ab.is_safe)
    
    def test_compare_mixed_changes(self):
        """Both recoveries and regressions."""
        before = EvaluationReport(total=4, passed=1, failed=3, results=[
            TestResult("test1", False, {"a": 1}, {"a": 0}),  # Will recover
            TestResult("test2", True, {"b": 2}, {"b": 2}),   # Will regress
            TestResult("test3", False, {"c": 3}, {"c": 0}),  # Will recover
            TestResult("test4", False, {"d": 4}, {"d": 0}),  # Will stay fail
        ])
        after = EvaluationReport(total=4, passed=2, failed=2, results=[
            TestResult("test1", True, {"a": 1}, {"a": 1}),
            TestResult("test2", False, {"b": 2}, {"b": 1}),
            TestResult("test3", True, {"c": 3}, {"c": 3}),
            TestResult("test4", False, {"d": 4}, {"d": 0}),
        ])
        
        ab = self.evaluator.compare(before, after)
        
        self.assertEqual(ab.before_pass_rate, 0.25)
        self.assertEqual(ab.after_pass_rate, 0.5)
        self.assertEqual(ab.pass_rate_delta, 0.25)
        self.assertEqual(ab.recovered_count, 2)
        self.assertEqual(ab.regressed_count, 1)
        self.assertEqual(ab.stable_pass_count, 0)
        self.assertEqual(ab.stable_fail_count, 1)
        self.assertFalse(ab.is_safe)
    
    def test_compare_new_fixtures_in_after(self):
        """After report has additional tests (union behavior)."""
        before = EvaluationReport(total=1, passed=1, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
        ])
        after = EvaluationReport(total=3, passed=2, failed=1, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
            TestResult("test2", True, {"y": 2}, {"y": 2}),
            TestResult("test3", False, {"z": 3}, {"z": 0}),
        ])
        
        ab = self.evaluator.compare(before, after)
        
        # A/B should track union: test1 (stable), test2 (new, pass=recovered), test3 (new, fail=stable_fail)
        self.assertEqual(len(ab.comparisons), 3)
        self.assertEqual(ab.stable_pass_count, 1)
        self.assertEqual(ab.recovered_count, 1)  # test2 was not in before (failed), now passes
        
        # Find test2 and test3 in comparisons
        test2 = next((c for c in ab.comparisons if c.fixture_name == "test2"), None)
        test3 = next((c for c in ab.comparisons if c.fixture_name == "test3"), None)
        
        self.assertIsNotNone(test2)
        self.assertIsNotNone(test3)
        self.assertEqual(test2.before_passed, False)  # Not in before, treated as failed
        self.assertEqual(test2.after_passed, True)
        self.assertEqual(test2.status, "recovered")
        self.assertEqual(test3.status, "stable_fail")
    
    def test_ab_report_to_dict(self):
        """ABReport serializes to dict."""
        before = EvaluationReport(total=1, passed=1, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
        ])
        after = EvaluationReport(total=1, passed=1, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
        ])
        
        ab = self.evaluator.compare(before, after)
        data = ab.to_dict()
        
        self.assertEqual(data["before_total"], 1)
        self.assertEqual(data["before_pass_rate"], 1.0)
        self.assertEqual(data["after_total"], 1)
        self.assertEqual(data["after_pass_rate"], 1.0)
        self.assertEqual(data["pass_rate_delta"], 0.0)
        self.assertEqual(data["recovered_count"], 0)
        self.assertEqual(data["regressed_count"], 0)
        self.assertTrue(data["is_safe"])
        self.assertIn("comparisons", data)
        self.assertEqual(len(data["comparisons"]), 1)
    
    def test_ab_report_comparison_details(self):
        """Comparison details include actual outputs for debugging."""
        before = EvaluationReport(total=1, passed=0, failed=1, results=[
            TestResult("test1", False, {"x": 1}, {"x": 0}, delta={"x": (0, 1)}),
        ])
        after = EvaluationReport(total=1, passed=1, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
        ])
        
        ab = self.evaluator.compare(before, after)
        data = ab.to_dict()
        
        comp = data["comparisons"][0]
        self.assertEqual(comp["fixture_name"], "test1")
        self.assertEqual(comp["status"], "recovered")
        self.assertEqual(comp["before_actual"], {"x": 0})
        self.assertEqual(comp["after_actual"], {"x": 1})


class ABReportPropertiesTests(unittest.TestCase):
    """Test ABReport property calculations."""
    
    def test_empty_reports(self):
        """Handle empty reports gracefully."""
        before = EvaluationReport(total=0, passed=0, failed=0, results=[])
        after = EvaluationReport(total=0, passed=0, failed=0, results=[])
        
        ab = ABReport(
            before_total=0,
            before_passed=0,
            after_total=0,
            after_passed=0,
        )
        
        self.assertEqual(ab.before_pass_rate, 0.0)
        self.assertEqual(ab.after_pass_rate, 0.0)
        self.assertEqual(ab.pass_rate_delta, 0.0)
        self.assertTrue(ab.is_safe)
    
    def test_pass_rate_with_single_test(self):
        """Pass rate calculation with one test."""
        before = EvaluationReport(total=1, passed=0, failed=1, results=[
            TestResult("test1", False, {"x": 1}, {"x": 0}),
        ])
        after = EvaluationReport(total=1, passed=1, failed=0, results=[
            TestResult("test1", True, {"x": 1}, {"x": 1}),
        ])
        
        ab = ABEvaluator().compare(before, after)
        
        self.assertEqual(ab.before_pass_rate, 0.0)
        self.assertEqual(ab.after_pass_rate, 1.0)
        self.assertEqual(ab.pass_rate_delta, 1.0)


if __name__ == "__main__":
    unittest.main()
