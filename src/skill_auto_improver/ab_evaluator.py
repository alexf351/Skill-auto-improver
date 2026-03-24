from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evaluator import EvaluationReport, TestResult


@dataclass(slots=True)
class ABComparison:
    """Result of comparing two evaluation reports (before/after)."""
    fixture_name: str
    before_passed: bool
    after_passed: bool
    before_actual: dict[str, Any]
    after_actual: dict[str, Any]
    status: str  # "recovered", "regressed", "stable_pass", "stable_fail"


@dataclass(slots=True)
class ABReport:
    """Summary of A/B evaluation comparing before and after skill states."""
    before_total: int
    before_passed: int
    after_total: int
    after_passed: int
    comparisons: list[ABComparison] = field(default_factory=list)
    
    @property
    def before_pass_rate(self) -> float:
        return self.before_passed / self.before_total if self.before_total > 0 else 0.0
    
    @property
    def after_pass_rate(self) -> float:
        return self.after_passed / self.after_total if self.after_total > 0 else 0.0
    
    @property
    def pass_rate_delta(self) -> float:
        """Improvement in pass rate (e.g., 0.5 → 0.8 = +0.3 delta)."""
        return self.after_pass_rate - self.before_pass_rate
    
    @property
    def recovered_count(self) -> int:
        """Tests that went from fail → pass."""
        return sum(1 for c in self.comparisons if c.status == "recovered")
    
    @property
    def regressed_count(self) -> int:
        """Tests that went from pass → fail (regressions)."""
        return sum(1 for c in self.comparisons if c.status == "regressed")
    
    @property
    def stable_pass_count(self) -> int:
        """Tests that passed both before and after."""
        return sum(1 for c in self.comparisons if c.status == "stable_pass")
    
    @property
    def stable_fail_count(self) -> int:
        """Tests that failed both before and after."""
        return sum(1 for c in self.comparisons if c.status == "stable_fail")
    
    @property
    def is_safe(self) -> bool:
        """True if no regressions detected."""
        return self.regressed_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_total": self.before_total,
            "before_passed": self.before_passed,
            "before_pass_rate": self.before_pass_rate,
            "after_total": self.after_total,
            "after_passed": self.after_passed,
            "after_pass_rate": self.after_pass_rate,
            "pass_rate_delta": self.pass_rate_delta,
            "recovered_count": self.recovered_count,
            "regressed_count": self.regressed_count,
            "stable_pass_count": self.stable_pass_count,
            "stable_fail_count": self.stable_fail_count,
            "is_safe": self.is_safe,
            "comparisons": [
                {
                    "fixture_name": c.fixture_name,
                    "before_passed": c.before_passed,
                    "after_passed": c.after_passed,
                    "status": c.status,
                    "before_actual": c.before_actual,
                    "after_actual": c.after_actual,
                }
                for c in self.comparisons
            ],
        }


class ABEvaluator:
    """Compare evaluation reports before and after skill amendments."""
    
    def __init__(self):
        pass
    
    def compare(
        self,
        before_report: EvaluationReport,
        after_report: EvaluationReport,
    ) -> ABReport:
        """
        Compare two evaluation reports.
        
        Args:
            before_report: Evaluation results from original skill
            after_report: Evaluation results after amendment
        
        Returns:
            ABReport with detailed comparisons, delta metrics, and regression detection
        """
        ab = ABReport(
            before_total=before_report.total,
            before_passed=before_report.passed,
            after_total=after_report.total,
            after_passed=after_report.passed,
        )
        
        # Build maps for quick lookup by fixture name
        before_map = {r.fixture_name: r for r in before_report.results}
        after_map = {r.fixture_name: r for r in after_report.results}
        
        # Compare all fixtures (union of before and after)
        all_fixtures = set(before_map.keys()) | set(after_map.keys())
        
        for fixture_name in sorted(all_fixtures):
            before_result = before_map.get(fixture_name)
            after_result = after_map.get(fixture_name)
            
            before_passed = before_result.passed if before_result else False
            after_passed = after_result.passed if after_result else False
            before_actual = before_result.actual if before_result else {}
            after_actual = after_result.actual if after_result else {}
            
            # Determine status
            if not before_passed and after_passed:
                status = "recovered"
            elif before_passed and not after_passed:
                status = "regressed"
            elif before_passed and after_passed:
                status = "stable_pass"
            else:
                status = "stable_fail"
            
            comparison = ABComparison(
                fixture_name=fixture_name,
                before_passed=before_passed,
                after_passed=after_passed,
                before_actual=before_actual,
                after_actual=after_actual,
                status=status,
            )
            ab.comparisons.append(comparison)
        
        return ab
