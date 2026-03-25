# Checklist-Based Evaluation Mode

Checklist mode adds a flexible yes/no question-based evaluation system to skill-auto-improver. This complements the existing fixture-based (golden test) mode, allowing you to:

- **Define simple 3-6 question checklists** for output quality validation
- **Score outputs 0-100%** based on question answers
- **Run in three modes**: fixture-only, checklist-only, or hybrid (both gates)
- **Use rule-based or LLM-based evaluation** with custom evaluator functions

## Quick Start

### 1. Define a Checklist

Create a JSON file with your checklist (e.g., `my_checklist.json`):

```json
{
  "name": "skill_quality_validation",
  "questions": [
    {
      "id": "q1_has_output",
      "question": "Does the output have meaningful content?",
      "description": "Verify output is not empty",
      "required": true
    },
    {
      "id": "q2_no_errors",
      "question": "Are there no error messages?",
      "description": "Check for absence of errors",
      "required": true
    },
    {
      "id": "q3_well_formatted",
      "question": "Is the output well-formatted?",
      "description": "Check structure and readability",
      "required": false
    }
  ]
}
```

### 2. Prepare Outputs to Evaluate

Create a JSON file with outputs (e.g., `outputs.json`):

```json
{
  "output_1": {
    "q1_has_output": true,
    "q2_no_errors": true,
    "q3_well_formatted": true,
    "text": "Successfully processed",
    "status": "ok"
  },
  "output_2": {
    "q1_has_output": true,
    "q2_no_errors": false,
    "q3_well_formatted": true,
    "text": "Processed with warnings",
    "error": "validation_warning"
  }
}
```

### 3. Evaluate via CLI

```bash
# Checklist-only mode
python3 -m skill_auto_improver.cli evaluate-checklist \
  --skill-path . \
  --checklist my_checklist.json \
  --outputs outputs.json

# Hybrid mode (both fixtures and checklist)
python3 -m skill_auto_improver.cli evaluate-hybrid \
  --skill-path . \
  --fixtures my_fixtures.json \
  --checklist my_checklist.json \
  --outputs outputs.json \
  --require-both  # Optional: require both gates to pass
```

## Evaluation Modes

### Mode 1: Rule-Based Evaluation (Default)

Simple pattern matching using output field values:

```python
from skill_auto_improver.checklist_evaluator import (
    ChecklistSpec, ChecklistQuestion, ChecklistEvaluator
)

checklist = ChecklistSpec(name="validation")
checklist.add_question(ChecklistQuestion(
    id="q1", question="Has name field?"
))

evaluator = ChecklistEvaluator(checklist)
result = evaluator.evaluate_snapshot({"q1": True})
print(f"Score: {result.score}%")  # 100.0
```

#### Pattern Matchers

The default rule-based evaluator supports these patterns:

- **Direct match**: `id` is a key in output and truthy
  ```json
  { "q1_valid": true }
  ```

- **Field check**: `has_field_NAME` checks if field exists
  ```json
  { "has_field_email": "john@example.com" }
  ```

- **Non-empty check**: `is_non_empty_NAME` checks if field exists and is non-empty
  ```json
  { "is_non_empty_description": "Some text" }
  ```

### Mode 2: Custom Evaluator (LLM-Based)

Use a custom function for complex evaluation logic:

```python
def evaluate_quality(output: dict, question) -> bool:
    text = output.get("text", "")
    
    if question.id == "is_concise":
        return len(text) < 100
    elif question.id == "has_greeting":
        return text.lower().startswith(("hello", "hi"))
    
    return False

evaluator = ChecklistEvaluator(checklist, evaluator_fn=evaluate_quality)
```

The evaluator function receives:
- `output`: The output dict being evaluated
- `question`: A `ChecklistQuestion` object with `id`, `question`, and `description`

And should return a boolean.

### Mode 3: Hybrid (Fixture + Checklist)

Combine both evaluation modes in one pass:

```python
from skill_auto_improver.loop import create_hybrid_evaluation_stage
from skill_auto_improver.evaluator import GoldenFixture

fixtures = [
    GoldenFixture(
        name="test1",
        input_data={},
        expected_output={"result": "ok"}
    )
]

stage = create_hybrid_evaluation_stage(
    fixtures=fixtures,
    checklist=checklist,
    require_both=False  # False = either/or, True = both required
)

result = stage({"actual_outputs": {...}})
print(result["passed"])  # True if criteria met
```

## Scoring

Each output is scored 0-100% based on questions answered:

- **100%**: All questions answered "yes"
- **50%**: Half the questions answered "yes"
- **0%**: No questions answered "yes"

### Example

```python
result = ChecklistResult(
    output_id="out1",
    checklist_name="validation",
    answers={"q1": True, "q2": True, "q3": False}
)

print(f"Score: {result.score:.1f}%")  # 66.7%
print(f"Passed all: {result.passed_all}")  # False
```

## Reports

Evaluation returns structured reports with aggregated metrics:

```python
report = evaluator.evaluate_all(outputs_dict)

print(f"Total outputs: {report.total_outputs}")
print(f"Passed all questions: {report.total_passed}")
print(f"Pass rate: {report.pass_rate:.1f}%")
print(f"Average score: {report.average_score:.1f}%")

for result in report.results:
    print(f"{result.output_id}: {result.score:.1f}%")
```

## Integration with Patch Trials

Checklist evaluation integrates with the safe-patch-trial workflow:

```python
from skill_auto_improver.loop import SkillAutoImprover, create_checklist_evaluator_stage

# Define evaluation stage using checklist
evaluate_stage = create_checklist_evaluator_stage(checklist)

# Or with custom evaluator
evaluate_stage = create_checklist_with_custom_evaluator_stage(
    checklist,
    evaluator_fn=my_custom_eval_fn
)

# Create improver with checklist evaluation
improver = SkillAutoImprover(
    observe=observe_stage,
    inspect=inspect_stage,
    amend=amend_stage,
    evaluate=evaluate_stage,
)

# Run trial
trace = improver.run_once(skill_path="./my-skill")
```

## Keep/Revert Logic

Checklist results follow the same keep/revert logic as fixtures:

1. **Before trial**: Evaluate before changes
2. **Apply patch**: Make proposed edits
3. **After trial**: Evaluate after changes
4. **Compare**: 
   - If all outputs pass checklist → **keep patch**
   - If any output fails checklist → **revert patch** (unless promoted baseline)

The decision is based on:
- Score threshold (all questions passing)
- Regression detection (before vs after comparison)
- Promotion profiles (protected fixtures may override)

## Examples

See `examples/checklist_example.py` for working examples:

```bash
cd skill-auto-improver
python3 examples/checklist_example.py
```

Also explore:
- `examples/sample_checklist.json` - Sample checklist definition
- `examples/sample_outputs.json` - Sample output data
- `examples/sample_fixtures.json` - Sample golden fixtures

## API Reference

### ChecklistQuestion

```python
@dataclass
class ChecklistQuestion:
    id: str                    # Unique identifier
    question: str              # The question to ask
    description: str = ""      # Detailed description
    required: bool = True      # True = must pass, False = optional
```

### ChecklistSpec

```python
@dataclass
class ChecklistSpec:
    name: str
    questions: list[ChecklistQuestion]
    
    def add_question(question: ChecklistQuestion) -> None: ...
    def to_dict() -> dict: ...
    @staticmethod
    def from_dict(d: dict) -> ChecklistSpec: ...
```

### ChecklistResult

```python
@dataclass
class ChecklistResult:
    output_id: str
    checklist_name: str
    answers: dict[str, bool]       # {question_id: yes/no}
    reason: str = ""
    
    @property
    def score() -> float:          # 0-100%
    @property
    def passed_all() -> bool:      # All answers yes?
```

### ChecklistEvaluationReport

```python
@dataclass
class ChecklistEvaluationReport:
    checklist_name: str
    total_outputs: int
    total_passed: int              # Count with passed_all=true
    results: list[ChecklistResult]
    
    @property
    def pass_rate() -> float:      # 0-100% (total_passed/total_outputs)
    @property
    def average_score() -> float:  # Mean of all result.score values
```

### ChecklistEvaluator

```python
class ChecklistEvaluator:
    def __init__(
        self,
        checklist: ChecklistSpec,
        evaluator_fn: Callable[[dict, ChecklistQuestion], bool] | None = None
    ): ...
    
    def evaluate_snapshot(output: dict, output_id: str = "default") -> ChecklistResult: ...
    def evaluate_all(outputs: list | dict) -> ChecklistEvaluationReport: ...
```

### ChecklistLoader

```python
class ChecklistLoader:
    @staticmethod
    def load_from_file(path: Path | str) -> ChecklistSpec: ...
    
    @staticmethod
    def load_from_dict(data: dict) -> ChecklistSpec: ...
```

## Hybrid Evaluation Function

```python
def create_hybrid_evaluation_stage(
    fixtures: list[GoldenFixture] | None = None,
    checklist: ChecklistSpec | None = None,
    require_both: bool = False,
) -> Stage:
    """
    Args:
        fixtures: Optional golden fixtures
        checklist: Optional checklist spec
        require_both: If True, both gates must pass (AND logic)
                     If False, either gate can pass (OR logic)
    
    Returns:
        A stage function that returns:
        {
            "fixture_evaluation": {...},
            "checklist_evaluation": {...},
            "mode": "fixture_only|checklist_only|hybrid_either_or|hybrid_both_required",
            "passed": bool
        }
    """
```

## Best Practices

1. **Keep checklists small**: 3-6 questions for clarity
2. **Make questions specific**: "Has description field?" not "Is good?"
3. **Use required=true for critical checks**: Must-haves vs nice-to-haves
4. **Test patterns first**: Verify rule-based patterns work before custom eval
5. **Document evaluators**: Comment custom evaluator logic clearly
6. **Version checklists**: Track checklist changes in git alongside skill changes

## Troubleshooting

**Q: Why is my score 0% even though answers look right?**
A: Ensure output keys match question IDs exactly (case-sensitive).

**Q: How do I use LLM evaluation?**
A: Pass `evaluator_fn=my_llm_evaluator` to `ChecklistEvaluator`. Your function must be `(dict, ChecklistQuestion) -> bool`.

**Q: Can I mix required and optional questions?**
A: Yes! `required=true` means the question must pass; `required=false` is informational. Both count toward the score.

**Q: What's the difference between checklist and fixture modes?**
A: 
- **Fixtures**: Exact output matching (before/after structural equality)
- **Checklists**: Quality gates (question-based yes/no evaluation)

You can use both together with hybrid mode!
