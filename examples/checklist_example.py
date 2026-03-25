"""
Example: Checklist-based evaluation for skill outputs.

Demonstrates how to:
1. Define a checklist with yes/no questions
2. Create a ChecklistEvaluator
3. Evaluate outputs against the checklist
4. Use rule-based and custom evaluators
5. Integrate with the hybrid evaluation stage
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.checklist_evaluator import (
    ChecklistSpec,
    ChecklistQuestion,
    ChecklistEvaluator,
)


def example_rule_based_evaluation():
    """
    Example 1: Rule-based evaluation using simple field checks.
    """
    print("\n=== Example 1: Rule-Based Checklist Evaluation ===\n")
    
    # Define a checklist for validating JSON output
    checklist = ChecklistSpec(name="json_validation")
    checklist.add_question(ChecklistQuestion(
        id="has_field_name",
        question="Does output have a 'name' field?",
        description="Output must include a name field",
        required=True,
    ))
    checklist.add_question(ChecklistQuestion(
        id="has_field_email",
        question="Does output have an 'email' field?",
        description="Output must include an email field",
        required=True,
    ))
    checklist.add_question(ChecklistQuestion(
        id="is_non_empty_description",
        question="Is the 'description' field non-empty?",
        description="Description must not be empty",
        required=False,
    ))
    
    # Create evaluator and test outputs
    evaluator = ChecklistEvaluator(checklist)
    
    outputs_to_test = {
        "output_pass": {
            "name": "John Doe",
            "email": "john@example.com",
            "description": "A great person",
        },
        "output_missing_email": {
            "name": "Jane Doe",
            "age": 30,
            "description": "Another person",
        },
        "output_empty_description": {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "description": "",
        },
    }
    
    # Evaluate all outputs
    report = evaluator.evaluate_all(outputs_to_test)
    
    print(f"Checklist: {report.checklist_name}")
    print(f"Total outputs: {report.total_outputs}")
    print(f"Outputs that passed ALL questions: {report.total_passed}")
    print(f"Pass rate (all questions): {report.pass_rate:.1f}%")
    print(f"Average score: {report.average_score:.1f}%\n")
    
    for result in report.results:
        print(f"Output: {result.output_id}")
        print(f"  Score: {result.score:.1f}%")
        print(f"  Passed all: {result.passed_all}")
        print(f"  Answers:")
        for q_id, answer in result.answers.items():
            status = "✓" if answer else "✗"
            print(f"    {status} {q_id}: {answer}")
        print()


def example_custom_evaluator():
    """
    Example 2: Custom evaluator function (e.g., for LLM-based evaluation).
    """
    print("\n=== Example 2: Custom Evaluator Function ===\n")
    
    # Define a checklist for validating text output
    checklist = ChecklistSpec(name="text_quality")
    checklist.add_question(ChecklistQuestion(
        id="is_concise",
        question="Is the output concise (under 100 chars)?",
    ))
    checklist.add_question(ChecklistQuestion(
        id="has_greeting",
        question="Does the output start with a greeting?",
    ))
    checklist.add_question(ChecklistQuestion(
        id="is_polite",
        question="Is the tone polite?",
    ))
    
    # Define custom evaluation logic
    def evaluate_text(output: dict, question):
        text = output.get("text", "")
        
        if question.id == "is_concise":
            return len(text) < 100
        elif question.id == "has_greeting":
            return text.lower().startswith(("hello", "hi", "greetings", "welcome"))
        elif question.id == "is_polite":
            polite_words = {"please", "thank", "appreciate", "kind"}
            return any(word in text.lower() for word in polite_words)
        
        return False
    
    # Create evaluator with custom function
    evaluator = ChecklistEvaluator(checklist, evaluator_fn=evaluate_text)
    
    test_outputs = {
        "response_1": {
            "text": "Hello! Thank you for your message. I appreciate you reaching out.",
        },
        "response_2": {
            "text": "This is a very long response that contains a lot of information and explanation, which makes it hard to understand quickly.",
        },
        "response_3": {
            "text": "Hi there! Please let me know if you need anything else.",
        },
    }
    
    report = evaluator.evaluate_all(test_outputs)
    
    print(f"Checklist: {report.checklist_name}")
    print(f"Average score: {report.average_score:.1f}%\n")
    
    for result in report.results:
        print(f"Response: {result.output_id}")
        print(f"  Score: {result.score:.1f}%")
        for q_id, answer in result.answers.items():
            status = "✓" if answer else "✗"
            print(f"    {status} {q_id}: {answer}")
        print()


def example_hybrid_evaluation():
    """
    Example 3: Hybrid evaluation with both fixture and checklist modes.
    """
    print("\n=== Example 3: Hybrid Evaluation (Fixture + Checklist) ===\n")
    
    from skill_auto_improver.evaluator import GoldenFixture, GoldenEvaluator
    from skill_auto_improver.loop import create_hybrid_evaluation_stage
    
    # Golden fixtures for structured testing
    fixtures = [
        GoldenFixture(
            name="test_basic",
            input_data={"query": "hello"},
            expected_output={"response": "hi", "confidence": 0.9},
        ),
    ]
    
    # Checklist for quality validation
    checklist = ChecklistSpec(name="quality_gate")
    checklist.add_question(ChecklistQuestion(
        id="has_field_response",
        question="Has response field?",
    ))
    checklist.add_question(ChecklistQuestion(
        id="has_field_confidence",
        question="Has confidence field?",
    ))
    
    # Create hybrid stage
    stage = create_hybrid_evaluation_stage(
        fixtures=fixtures,
        checklist=checklist,
        require_both=False,  # Either fixture OR checklist can pass
    )
    
    # Test data
    context = {
        "actual_outputs": {
            "test_basic": {"response": "hi", "confidence": 0.9},
        }
    }
    
    result = stage(context)
    
    print(f"Mode: {result.get('mode')}")
    print(f"Overall passed: {result.get('passed')}")
    print(f"Fixture evaluation: {result.get('fixture_evaluation', {}).get('passed')}/{result.get('fixture_evaluation', {}).get('total')}")
    print(f"Checklist evaluation: {result.get('checklist_evaluation', {}).get('total_passed')}/{result.get('checklist_evaluation', {}).get('total_outputs')}")


if __name__ == "__main__":
    example_rule_based_evaluation()
    example_custom_evaluator()
    example_hybrid_evaluation()
    
    print("\n" + "="*60)
    print("All examples completed successfully!")
    print("="*60)
