from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.evaluator import (
    GoldenFixture,
    GoldenFixtureLoader,
    GoldenEvaluator,
    EvaluationReport,
)


class GoldenFixtureLoaderTests(unittest.TestCase):
    def test_load_from_dict(self):
        fixtures_data = [
            {
                "name": "test_basic",
                "input_data": {"query": "hello"},
                "expected_output": {"response": "hi"},
                "tags": ["smoke"],
            },
            {
                "name": "test_complex",
                "input_data": {"data": [1, 2, 3]},
                "expected_output": {"sum": 6},
            },
        ]
        fixtures = GoldenFixtureLoader.load_from_dict(fixtures_data)
        self.assertEqual(len(fixtures), 2)
        self.assertEqual(fixtures[0].name, "test_basic")
        self.assertEqual(fixtures[0].tags, ["smoke"])
        self.assertEqual(fixtures[1].expected_output["sum"], 6)

    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures_file = Path(tmp) / "fixtures.json"
            fixtures_data = [
                {"name": "test_a", "input_data": {}, "expected_output": {"result": "pass"}},
            ]
            fixtures_file.write_text(json.dumps(fixtures_data), encoding="utf-8")

            fixtures = GoldenFixtureLoader.load_from_file(fixtures_file)
            self.assertEqual(len(fixtures), 1)
            self.assertEqual(fixtures[0].name, "test_a")

    def test_load_from_missing_file_returns_empty(self):
        fixtures = GoldenFixtureLoader.load_from_file("/nonexistent/path.json")
        self.assertEqual(fixtures, [])


class GoldenEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = [
            GoldenFixture(
                name="test_hello",
                input_data={"query": "hello"},
                expected_output={"response": "hi"},
            ),
            GoldenFixture(
                name="test_math",
                input_data={"a": 1, "b": 2},
                expected_output={"sum": 3, "product": 2},
            ),
        ]
        self.evaluator = GoldenEvaluator(self.fixtures)

    def test_evaluate_snapshot_passes_on_match(self):
        actual = {"response": "hi"}
        result = self.evaluator.evaluate_snapshot(actual, fixture_name="test_hello")
        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "Match")
        self.assertEqual(result.delta, {})

    def test_evaluate_snapshot_fails_on_mismatch(self):
        actual = {"response": "hello"}
        result = self.evaluator.evaluate_snapshot(actual, fixture_name="test_hello")
        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "Mismatch")
        self.assertIn("response", result.delta)
        self.assertEqual(result.delta["response"]["expected"], "hi")
        self.assertEqual(result.delta["response"]["actual"], "hello")

    def test_evaluate_snapshot_handles_missing_keys(self):
        actual = {"response": "hi", "extra": "field"}
        result = self.evaluator.evaluate_snapshot(actual, fixture_name="test_hello")
        self.assertFalse(result.passed)
        self.assertIn("extra", result.delta)
        self.assertEqual(result.delta["extra"]["expected"], "<missing>")

    def test_evaluate_all_with_dict_input(self):
        actuals = {
            "test_hello": {"response": "hi"},
            "test_math": {"sum": 3, "product": 2},
        }
        report = self.evaluator.evaluate_all(actuals)
        self.assertEqual(report.total, 2)
        self.assertEqual(report.passed, 2)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.pass_rate, 1.0)

    def test_evaluate_all_with_list_input(self):
        actuals = [
            {"response": "hi"},
            {"sum": 3, "product": 2},
        ]
        report = self.evaluator.evaluate_all(actuals)
        self.assertEqual(report.total, 2)
        self.assertEqual(report.passed, 2)
        self.assertEqual(report.failed, 0)

    def test_evaluate_all_mixed_pass_fail(self):
        actuals = [
            {"response": "hi"},
            {"sum": 4, "product": 2},  # wrong sum
        ]
        report = self.evaluator.evaluate_all(actuals)
        self.assertEqual(report.total, 2)
        self.assertEqual(report.passed, 1)
        self.assertEqual(report.failed, 1)
        self.assertAlmostEqual(report.pass_rate, 0.5)

    def test_evaluation_report_to_dict(self):
        actuals = [{"response": "hi"}, {"sum": 4, "product": 2}]
        report = self.evaluator.evaluate_all(actuals)
        d = report.to_dict()
        self.assertEqual(d["total"], 2)
        self.assertEqual(d["passed"], 1)
        self.assertEqual(d["failed"], 1)
        self.assertIn("pass_rate", d)
        self.assertIn("results", d)
        self.assertEqual(len(d["results"]), 2)

    def test_evaluate_with_no_fixtures_loaded(self):
        evaluator = GoldenEvaluator([])
        result = evaluator.evaluate_snapshot({"some": "data"})
        self.assertFalse(result.passed)
        self.assertIn("No fixtures", result.reason)


if __name__ == "__main__":
    unittest.main()
