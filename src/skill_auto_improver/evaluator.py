from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(slots=True)
class GoldenFixture:
    """A single test case with expected input and output."""
    name: str
    input_data: dict[str, Any]
    expected_output: dict[str, Any]
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TestResult:
    """Result of evaluating one fixture."""
    fixture_name: str
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    delta: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(slots=True)
class EvaluationReport:
    """Summary of all evaluations in a run."""
    total: int
    passed: int
    failed: int
    results: list[TestResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "results": [
                {
                    "fixture_name": r.fixture_name,
                    "passed": r.passed,
                    "expected": r.expected,
                    "actual": r.actual,
                    "delta": r.delta,
                    "reason": r.reason,
                }
                for r in self.results
            ],
        }


class GoldenFixtureLoader:
    """Load golden test fixtures from JSON or Python dict."""

    @staticmethod
    def load_from_file(path: Path | str) -> list[GoldenFixture]:
        """Load fixtures from a JSON file: [{"name": "...", "input_data": {...}, "expected_output": {...}}]"""
        path = Path(path)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            GoldenFixture(
                name=f["name"],
                input_data=f.get("input_data", {}),
                expected_output=f.get("expected_output", {}),
                tags=f.get("tags", []),
            )
            for f in data
        ]

    @staticmethod
    def load_from_dict(fixtures: list[dict[str, Any]]) -> list[GoldenFixture]:
        """Load fixtures from a list of dicts."""
        return [
            GoldenFixture(
                name=f["name"],
                input_data=f.get("input_data", {}),
                expected_output=f.get("expected_output", {}),
                tags=f.get("tags", []),
            )
            for f in fixtures
        ]


class GoldenEvaluator:
    """
    Evaluates before/after outputs against golden fixtures.
    Computes pass/fail + delta for trace logging.
    """

    def __init__(self, fixtures: list[GoldenFixture]):
        self.fixtures = fixtures

    def evaluate_snapshot(
        self, actual_output: dict[str, Any], fixture_name: str | None = None
    ) -> TestResult:
        """
        Score a single actual output against one fixture.
        If fixture_name is None, match by first fixture.
        """
        if not self.fixtures:
            return TestResult(
                fixture_name="<unknown>",
                passed=False,
                expected={},
                actual=actual_output,
                reason="No fixtures loaded",
            )

        if fixture_name:
            fixture = next((f for f in self.fixtures if f.name == fixture_name), None)
        else:
            fixture = self.fixtures[0]

        if fixture is None:
            return TestResult(
                fixture_name=fixture_name or "<unknown>",
                passed=False,
                expected={},
                actual=actual_output,
                reason=f"Fixture '{fixture_name}' not found",
            )

        passed = actual_output == fixture.expected_output
        delta = self._compute_delta(fixture.expected_output, actual_output)

        return TestResult(
            fixture_name=fixture.name,
            passed=passed,
            expected=fixture.expected_output,
            actual=actual_output,
            delta=delta,
            reason="Match" if passed else "Mismatch",
        )

    def evaluate_all(
        self, actual_outputs: dict[str, dict[str, Any]] | list[dict[str, Any]]
    ) -> EvaluationReport:
        """
        Evaluate multiple outputs against all fixtures.
        If dict: match by fixture name.
        If list: match sequentially.
        """
        results = []
        if isinstance(actual_outputs, dict):
            for fixture in self.fixtures:
                actual = actual_outputs.get(fixture.name, {})
                result = self.evaluate_snapshot(actual, fixture_name=fixture.name)
                results.append(result)
        else:
            for i, actual in enumerate(actual_outputs):
                fixture = self.fixtures[i] if i < len(self.fixtures) else None
                if fixture is None:
                    result = TestResult(
                        fixture_name=f"<extra_{i}>",
                        passed=False,
                        expected={},
                        actual=actual,
                        reason="Extra output, no fixture",
                    )
                else:
                    result = self.evaluate_snapshot(actual, fixture_name=fixture.name)
                results.append(result)

        passed = sum(1 for r in results if r.passed)
        report = EvaluationReport(total=len(results), passed=passed, failed=len(results) - passed)
        report.results = results
        return report

    @staticmethod
    def _compute_delta(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
        """
        Compute a simple diff between expected and actual outputs.
        Returns a dict showing missing, extra, and changed keys.
        """
        delta = {}
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in all_keys:
            exp_val = expected.get(key, "<missing>")
            act_val = actual.get(key, "<missing>")
            if exp_val != act_val:
                delta[key] = {"expected": exp_val, "actual": act_val}
        return delta
