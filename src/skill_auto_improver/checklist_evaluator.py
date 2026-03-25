from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json


@dataclass(slots=True)
class ChecklistQuestion:
    """A single yes/no question for checklist-based evaluation."""
    id: str
    question: str
    description: str = ""
    required: bool = True


@dataclass(slots=True)
class ChecklistSpec:
    """Collection of questions forming a checklist."""
    name: str
    questions: list[ChecklistQuestion] = field(default_factory=list)
    
    def add_question(self, question: ChecklistQuestion) -> None:
        """Add a question to the checklist."""
        self.questions.append(question)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "questions": [
                {"id": q.id, "question": q.question, "description": q.description, "required": q.required}
                for q in self.questions
            ],
        }
    
    @staticmethod
    def from_dict(d: dict[str, Any]) -> ChecklistSpec:
        """Load a checklist spec from a dict."""
        questions = [
            ChecklistQuestion(
                id=q.get("id", ""),
                question=q.get("question", ""),
                description=q.get("description", ""),
                required=q.get("required", True),
            )
            for q in d.get("questions", [])
        ]
        return ChecklistSpec(name=d.get("name", ""), questions=questions)


@dataclass(slots=True)
class ChecklistResult:
    """Result of evaluating an output against a checklist."""
    output_id: str
    checklist_name: str
    answers: dict[str, bool] = field(default_factory=dict)
    reason: str = ""
    
    @property
    def score(self) -> float:
        """Return score as 0-100%."""
        if not self.answers:
            return 0.0
        passed = sum(1 for v in self.answers.values() if v)
        return (passed / len(self.answers)) * 100.0
    
    @property
    def passed_all(self) -> bool:
        """True if all answers are yes."""
        return all(self.answers.values()) if self.answers else False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "checklist_name": self.checklist_name,
            "answers": self.answers,
            "reason": self.reason,
            "score": self.score,
            "passed_all": self.passed_all,
        }


@dataclass(slots=True)
class ChecklistEvaluationReport:
    """Summary of checklist-based evaluations."""
    checklist_name: str
    total_outputs: int
    total_passed: int
    results: list[ChecklistResult] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        """Return overall pass rate 0.0-1.0 (not percentage)."""
        return (self.total_passed / self.total_outputs) if self.total_outputs > 0 else 0.0
    
    @property
    def average_score(self) -> float:
        """Return average score across all results."""
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "checklist_name": self.checklist_name,
            "total_outputs": self.total_outputs,
            "total_passed": self.total_passed,
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
            "results": [r.to_dict() for r in self.results],
        }


class ChecklistLoader:
    """Load checklist specs from JSON or Python dicts."""
    
    @staticmethod
    def load_from_file(path: Path | str) -> ChecklistSpec:
        """Load a checklist spec from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Checklist file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ChecklistSpec.from_dict(data)
    
    @staticmethod
    def load_from_dict(data: dict[str, Any]) -> ChecklistSpec:
        """Load a checklist spec from a dict."""
        return ChecklistSpec.from_dict(data)


class ChecklistEvaluator:
    """
    Evaluates outputs against a checklist of yes/no questions.
    Supports both LLM-based and rule-based evaluation.
    """
    
    def __init__(
        self,
        checklist: ChecklistSpec,
        evaluator_fn: Callable[[dict[str, Any], ChecklistQuestion], bool] | None = None,
    ):
        """
        Args:
            checklist: The checklist spec with questions
            evaluator_fn: Optional function(output, question) -> bool.
                         If None, uses rule-based evaluation.
        """
        self.checklist = checklist
        self.evaluator_fn = evaluator_fn
    
    def evaluate_snapshot(
        self,
        output: dict[str, Any],
        output_id: str = "default",
    ) -> ChecklistResult:
        """
        Evaluate a single output against the checklist.
        Returns a ChecklistResult with yes/no answers and a score.
        """
        answers: dict[str, bool] = {}
        
        if self.evaluator_fn:
            # LLM-based evaluation
            for question in self.checklist.questions:
                try:
                    answer = self.evaluator_fn(output, question)
                    answers[question.id] = bool(answer)
                except Exception as e:
                    answers[question.id] = False
                    reason = f"Error evaluating {question.id}: {str(e)}"
        else:
            # Rule-based evaluation (simple checks)
            for question in self.checklist.questions:
                answer = self._rule_based_eval(output, question)
                answers[question.id] = answer
        
        result = ChecklistResult(
            output_id=output_id,
            checklist_name=self.checklist.name,
            answers=answers,
        )
        return result
    
    def evaluate_all(
        self,
        outputs: list[dict[str, Any]] | dict[str, dict[str, Any]],
    ) -> ChecklistEvaluationReport:
        """
        Evaluate multiple outputs against the checklist.
        
        Args:
            outputs: List of dicts or dict of {output_id: output_dict}
        
        Returns:
            ChecklistEvaluationReport with results and aggregated scores
        """
        results = []
        
        if isinstance(outputs, dict):
            for output_id, output in outputs.items():
                result = self.evaluate_snapshot(output, output_id=output_id)
                results.append(result)
        else:
            for i, output in enumerate(outputs):
                output_id = f"output_{i}"
                result = self.evaluate_snapshot(output, output_id=output_id)
                results.append(result)
        
        total_passed = sum(1 for r in results if r.passed_all)
        report = ChecklistEvaluationReport(
            checklist_name=self.checklist.name,
            total_outputs=len(results),
            total_passed=total_passed,
            results=results,
        )
        return report
    
    @staticmethod
    def _rule_based_eval(output: dict[str, Any], question: ChecklistQuestion) -> bool:
        """
        Simple rule-based evaluation. Override or use custom evaluator_fn for complex logic.
        
        This checks:
        - If question.id exists as a key in output and is truthy
        - If it matches common patterns (e.g., "has_field_X" -> checks for field X)
        """
        question_id = question.id
        
        # Direct match: question_id is a key in output and truthy
        if question_id in output and output[question_id]:
            return True
        
        # Pattern: "has_field_X" -> check if "X" exists in output
        if question_id.startswith("has_field_"):
            field_name = question_id[len("has_field_"):]
            return field_name in output and output[field_name] is not None
        
        # Pattern: "is_non_empty_X" -> check if "X" exists and is non-empty
        if question_id.startswith("is_non_empty_"):
            field_name = question_id[len("is_non_empty_"):]
            val = output.get(field_name)
            return bool(val) if val is not None else False
        
        # Default: False if not found
        return False
