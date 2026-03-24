"""
Example: Using the golden evaluator to assess skill improvements.

This shows the MVP pattern:
  1. Define golden test fixtures (expected inputs/outputs)
  2. Run a skill and capture its outputs
  3. Evaluate against fixtures to get pass/fail + delta
  4. Log results in the trace
"""

import sys
from pathlib import Path

# Add src to path for example
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.evaluator import (
    GoldenFixture,
    GoldenEvaluator,
    GoldenFixtureLoader,
)
from skill_auto_improver.loop import SkillAutoImprover, create_golden_evaluator_stage


def example_1_basic_evaluation():
    """Minimal example: evaluate outputs against golden fixtures."""
    print("\n=== Example 1: Basic Evaluation ===\n")

    # Define golden test cases
    fixtures = [
        GoldenFixture(
            name="string_reversal",
            input_data={"text": "hello"},
            expected_output={"reversed": "olleh"},
        ),
        GoldenFixture(
            name="sum_numbers",
            input_data={"numbers": [1, 2, 3]},
            expected_output={"sum": 6},
        ),
    ]

    # Simulate skill outputs (some pass, some fail)
    actual_outputs = {
        "string_reversal": {"reversed": "olleh"},  # PASS
        "sum_numbers": {"sum": 7},  # FAIL (expected 6)
    }

    # Evaluate
    evaluator = GoldenEvaluator(fixtures)
    report = evaluator.evaluate_all(actual_outputs)

    print(f"Evaluation Report:")
    print(f"  Total: {report.total}")
    print(f"  Passed: {report.passed}")
    print(f"  Failed: {report.failed}")
    print(f"  Pass Rate: {report.pass_rate:.1%}\n")

    for result in report.results:
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"  {status}: {result.fixture_name}")
        if result.delta:
            print(f"    Delta: {result.delta}")


def example_2_full_loop_with_evaluation():
    """Full example: observe → inspect → amend → evaluate loop."""
    print("\n=== Example 2: Full Loop with Evaluation ===\n")

    # Golden fixtures for the skill
    fixtures = [
        GoldenFixture(
            name="increment",
            input_data={"x": 5},
            expected_output={"result": 6},
        ),
        GoldenFixture(
            name="double",
            input_data={"x": 3},
            expected_output={"result": 6},
        ),
    ]

    # Define stages
    def observe(context):
        """Observe: check the skill's current behavior."""
        return {"behavior": "multiplies by 2 (buggy for increment case)"}

    def inspect(context):
        """Inspect: analyze failure patterns."""
        return {"issue": "increment case returns 10 instead of 6"}

    def amend(context):
        """Amend: propose a fix (in real scenario, this might be AI-generated)."""
        return {
            "patch": "Add conditional: if operation=='increment', return x+1",
            "confidence": 0.8,
        }

    # Create evaluator stage (simulating fixed behavior)
    evaluator_stage = create_golden_evaluator_stage(fixtures)

    # Run the loop
    improver = SkillAutoImprover(
        observe=observe,
        inspect=inspect,
        amend=amend,
        evaluate=evaluator_stage,
    )

    trace = improver.run_once(
        skill_path="/tmp/example_skill",
        logs_dir="/tmp/example_runs",
    )

    print(f"Loop completed with status: {trace.status}")
    print(f"Steps executed: {[s.name for s in trace.steps]}\n")

    for step in trace.steps:
        print(f"{step.name.upper()}:")
        for key, value in step.output.items():
            print(f"  {key}: {value}")
        print()


def example_3_load_from_file():
    """Load golden fixtures from a JSON file."""
    print("\n=== Example 3: Load from JSON File ===\n")

    import json
    import tempfile

    # Create a sample fixtures file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        fixtures_data = [
            {
                "name": "greeting",
                "input_data": {"name": "Alice"},
                "expected_output": {"greeting": "Hello, Alice!"},
                "tags": ["smoke"],
            },
            {
                "name": "math",
                "input_data": {"a": 10, "b": 20},
                "expected_output": {"sum": 30},
                "tags": ["unit"],
            },
        ]
        json.dump(fixtures_data, f)
        fixtures_file = f.name

    # Load from file
    fixtures = GoldenFixtureLoader.load_from_file(fixtures_file)
    print(f"Loaded {len(fixtures)} fixtures from {fixtures_file}\n")

    for fixture in fixtures:
        print(f"  {fixture.name}: tags={fixture.tags}")
        print(f"    input: {fixture.input_data}")
        print(f"    expected: {fixture.expected_output}\n")

    # Clean up
    Path(fixtures_file).unlink()


if __name__ == "__main__":
    example_1_basic_evaluation()
    example_2_full_loop_with_evaluation()
    example_3_load_from_file()
    print("\n✓ Examples complete!")
