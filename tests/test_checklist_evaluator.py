from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.checklist_evaluator import (
    ChecklistQuestion,
    ChecklistSpec,
    ChecklistResult,
    ChecklistEvaluationReport,
    ChecklistLoader,
    ChecklistEvaluator,
)


class ChecklistQuestionTests(unittest.TestCase):
    def test_create_question(self):
        q = ChecklistQuestion(
            id="q1",
            question="Is the output valid?",
            description="Check if output format is valid",
            required=True,
        )
        self.assertEqual(q.id, "q1")
        self.assertEqual(q.question, "Is the output valid?")
        self.assertTrue(q.required)

    def test_question_optional(self):
        q = ChecklistQuestion(id="q2", question="Is the output optimized?", required=False)
        self.assertFalse(q.required)


class ChecklistSpecTests(unittest.TestCase):
    def test_create_checklist(self):
        checklist = ChecklistSpec(name="validation")
        self.assertEqual(checklist.name, "validation")
        self.assertEqual(len(checklist.questions), 0)

    def test_add_question(self):
        checklist = ChecklistSpec(name="test")
        q1 = ChecklistQuestion(id="q1", question="Question 1?")
        q2 = ChecklistQuestion(id="q2", question="Question 2?")
        
        checklist.add_question(q1)
        checklist.add_question(q2)
        
        self.assertEqual(len(checklist.questions), 2)
        self.assertEqual(checklist.questions[0].id, "q1")
        self.assertEqual(checklist.questions[1].id, "q2")

    def test_to_dict(self):
        checklist = ChecklistSpec(name="test")
        checklist.add_question(ChecklistQuestion(id="q1", question="Q1?", description="Desc1"))
        
        d = checklist.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(len(d["questions"]), 1)
        self.assertEqual(d["questions"][0]["id"], "q1")
        self.assertEqual(d["questions"][0]["description"], "Desc1")

    def test_from_dict(self):
        d = {
            "name": "my_checklist",
            "questions": [
                {"id": "q1", "question": "Q1?", "description": "D1", "required": True},
                {"id": "q2", "question": "Q2?", "description": "D2", "required": False},
            ],
        }
        checklist = ChecklistSpec.from_dict(d)
        self.assertEqual(checklist.name, "my_checklist")
        self.assertEqual(len(checklist.questions), 2)
        self.assertTrue(checklist.questions[0].required)
        self.assertFalse(checklist.questions[1].required)


class ChecklistResultTests(unittest.TestCase):
    def test_score_all_pass(self):
        result = ChecklistResult(
            output_id="out1",
            checklist_name="test",
            answers={"q1": True, "q2": True, "q3": True},
        )
        self.assertEqual(result.score, 100.0)
        self.assertTrue(result.passed_all)

    def test_score_partial_pass(self):
        result = ChecklistResult(
            output_id="out1",
            checklist_name="test",
            answers={"q1": True, "q2": False, "q3": True},
        )
        self.assertAlmostEqual(result.score, 66.67, places=1)
        self.assertFalse(result.passed_all)

    def test_score_all_fail(self):
        result = ChecklistResult(
            output_id="out1",
            checklist_name="test",
            answers={"q1": False, "q2": False},
        )
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.passed_all)

    def test_score_empty_answers(self):
        result = ChecklistResult(
            output_id="out1",
            checklist_name="test",
            answers={},
        )
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.passed_all)

    def test_to_dict(self):
        result = ChecklistResult(
            output_id="out1",
            checklist_name="test",
            answers={"q1": True, "q2": False},
            reason="Manual evaluation",
        )
        d = result.to_dict()
        self.assertEqual(d["output_id"], "out1")
        self.assertEqual(d["checklist_name"], "test")
        self.assertEqual(d["answers"], {"q1": True, "q2": False})
        self.assertEqual(d["reason"], "Manual evaluation")
        self.assertAlmostEqual(d["score"], 50.0, places=1)


class ChecklistEvaluationReportTests(unittest.TestCase):
    def test_pass_rate(self):
        results = [
            ChecklistResult("out1", "test", answers={"q": True}, reason="Pass"),
            ChecklistResult("out2", "test", answers={"q": False}, reason="Fail"),
            ChecklistResult("out3", "test", answers={"q": True}, reason="Pass"),
        ]
        report = ChecklistEvaluationReport(
            checklist_name="test",
            total_outputs=3,
            total_passed=2,
            results=results,
        )
        self.assertAlmostEqual(report.pass_rate, 0.6667, places=3)

    def test_average_score(self):
        results = [
            ChecklistResult("out1", "test", answers={"q1": True, "q2": True}),  # 100%
            ChecklistResult("out2", "test", answers={"q1": True, "q2": False}),  # 50%
            ChecklistResult("out3", "test", answers={"q1": False, "q2": False}),  # 0%
        ]
        report = ChecklistEvaluationReport(
            checklist_name="test",
            total_outputs=3,
            total_passed=1,
            results=results,
        )
        self.assertAlmostEqual(report.average_score, 50.0, places=1)

    def test_to_dict(self):
        results = [
            ChecklistResult("out1", "test", answers={"q": True}),
            ChecklistResult("out2", "test", answers={"q": False}),
        ]
        report = ChecklistEvaluationReport(
            checklist_name="test",
            total_outputs=2,
            total_passed=1,
            results=results,
        )
        d = report.to_dict()
        self.assertEqual(d["checklist_name"], "test")
        self.assertEqual(d["total_outputs"], 2)
        self.assertEqual(d["total_passed"], 1)
        self.assertEqual(len(d["results"]), 2)


class ChecklistLoaderTests(unittest.TestCase):
    def test_load_from_dict(self):
        data = {
            "name": "validation",
            "questions": [
                {"id": "q1", "question": "Valid?", "required": True},
                {"id": "q2", "question": "Complete?", "required": False},
            ],
        }
        checklist = ChecklistLoader.load_from_dict(data)
        self.assertEqual(checklist.name, "validation")
        self.assertEqual(len(checklist.questions), 2)

    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            checklist_path = Path(tmpdir) / "checklist.json"
            data = {
                "name": "test_checklist",
                "questions": [
                    {"id": "q1", "question": "Q1?"},
                    {"id": "q2", "question": "Q2?"},
                ],
            }
            checklist_path.write_text(json.dumps(data), encoding="utf-8")
            
            checklist = ChecklistLoader.load_from_file(checklist_path)
            self.assertEqual(checklist.name, "test_checklist")
            self.assertEqual(len(checklist.questions), 2)

    def test_load_from_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            ChecklistLoader.load_from_file("/nonexistent/path.json")


class ChecklistEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.checklist = ChecklistSpec(name="validation")
        self.checklist.add_question(ChecklistQuestion(id="q1", question="Has name?"))
        self.checklist.add_question(ChecklistQuestion(id="q2", question="Has email?"))
        self.checklist.add_question(ChecklistQuestion(id="q3", question="Is valid?"))

    def test_evaluate_snapshot_with_rule_based(self):
        """Test rule-based evaluation (direct key match)."""
        evaluator = ChecklistEvaluator(self.checklist)
        
        output = {
            "q1": True,
            "q2": True,
            "q3": False,
        }
        result = evaluator.evaluate_snapshot(output, output_id="test1")
        
        self.assertEqual(result.output_id, "test1")
        self.assertEqual(result.answers["q1"], True)
        self.assertEqual(result.answers["q2"], True)
        self.assertEqual(result.answers["q3"], False)
        self.assertAlmostEqual(result.score, 66.67, places=1)

    def test_evaluate_snapshot_with_custom_evaluator(self):
        """Test custom LLM-based evaluator."""
        def custom_eval(output: dict, question: ChecklistQuestion) -> bool:
            # Check if output has "text" field and it contains "valid"
            if question.id == "q1":
                return "text" in output and len(output.get("text", "")) > 0
            if question.id == "q2":
                return "email" in output
            if question.id == "q3":
                text = output.get("text", "")
                return "valid" in text.lower()
            return False
        
        evaluator = ChecklistEvaluator(self.checklist, evaluator_fn=custom_eval)
        
        output = {
            "text": "This is valid data",
            "email": "test@example.com",
        }
        result = evaluator.evaluate_snapshot(output, output_id="test1")
        
        self.assertTrue(result.answers["q1"])  # has text
        self.assertTrue(result.answers["q2"])  # has email
        self.assertTrue(result.answers["q3"])  # text contains "valid"
        self.assertEqual(result.score, 100.0)

    def test_evaluate_snapshot_has_field_pattern(self):
        """Test rule-based evaluation with has_field_* pattern."""
        checklist = ChecklistSpec(name="field_test")
        checklist.add_question(ChecklistQuestion(id="has_field_name", question="Has name field?"))
        checklist.add_question(ChecklistQuestion(id="has_field_email", question="Has email field?"))
        
        evaluator = ChecklistEvaluator(checklist)
        
        output = {
            "name": "John",
            "age": 30,
        }
        result = evaluator.evaluate_snapshot(output)
        
        self.assertTrue(result.answers["has_field_name"])
        self.assertFalse(result.answers["has_field_email"])

    def test_evaluate_snapshot_is_non_empty_pattern(self):
        """Test rule-based evaluation with is_non_empty_* pattern."""
        checklist = ChecklistSpec(name="non_empty_test")
        checklist.add_question(ChecklistQuestion(id="is_non_empty_description", question="Has description?"))
        checklist.add_question(ChecklistQuestion(id="is_non_empty_tags", question="Has tags?"))
        
        evaluator = ChecklistEvaluator(checklist)
        
        output = {
            "description": "Some text",
            "tags": [],
        }
        result = evaluator.evaluate_snapshot(output)
        
        self.assertTrue(result.answers["is_non_empty_description"])
        self.assertFalse(result.answers["is_non_empty_tags"])

    def test_evaluate_all_list_input(self):
        """Test evaluating multiple outputs from a list."""
        evaluator = ChecklistEvaluator(self.checklist)
        
        outputs = [
            {"q1": True, "q2": True, "q3": True},
            {"q1": True, "q2": False, "q3": True},
            {"q1": False, "q2": False, "q3": False},
        ]
        report = evaluator.evaluate_all(outputs)
        
        self.assertEqual(report.total_outputs, 3)
        self.assertEqual(report.total_passed, 1)  # Only first one passes all
        self.assertAlmostEqual(report.pass_rate, 0.3333, places=3)
        self.assertEqual(len(report.results), 3)

    def test_evaluate_all_dict_input(self):
        """Test evaluating multiple outputs from a dict."""
        evaluator = ChecklistEvaluator(self.checklist)
        
        outputs = {
            "before": {"q1": True, "q2": True, "q3": True},
            "after": {"q1": True, "q2": False, "q3": True},
        }
        report = evaluator.evaluate_all(outputs)
        
        self.assertEqual(report.total_outputs, 2)
        self.assertEqual(report.total_passed, 1)
        self.assertEqual(report.results[0].output_id, "before")
        self.assertEqual(report.results[1].output_id, "after")

    def test_evaluate_with_exception_handling(self):
        """Test that custom evaluator exceptions are caught."""
        def broken_eval(output: dict, question: ChecklistQuestion) -> bool:
            raise ValueError("Broken evaluator")
        
        evaluator = ChecklistEvaluator(self.checklist, evaluator_fn=broken_eval)
        result = evaluator.evaluate_snapshot({})
        
        # Should catch exception and return False for all
        self.assertFalse(result.passed_all)
        self.assertTrue(all(v is False for v in result.answers.values()))


if __name__ == "__main__":
    unittest.main()
