# Checklist Mode Quick Start

Get started with checklist-based evaluation in 5 minutes.

## 1. Create Your Checklist

Save as `checklist.json`:

```json
{
  "name": "code_quality",
  "questions": [
    {
      "id": "q1_compiles",
      "question": "Does the code compile without errors?",
      "required": true
    },
    {
      "id": "q2_has_docstring",
      "question": "Are functions documented?",
      "required": true
    },
    {
      "id": "q3_tests_pass",
      "question": "Do all tests pass?",
      "required": false
    }
  ]
}
```

## 2. Define Outputs to Evaluate

Save as `outputs.json`:

```json
{
  "output_v1": {
    "q1_compiles": true,
    "q2_has_docstring": true,
    "q3_tests_pass": true
  },
  "output_v2": {
    "q1_compiles": true,
    "q2_has_docstring": false,
    "q3_tests_pass": true
  }
}
```

## 3. Run Evaluation (CLI)

```bash
python3 -c "
import sys
sys.path.insert(0, 'src')
from skill_auto_improver.cli import main
sys.exit(main([
  'evaluate-checklist',
  '--skill-path', '.',
  '--checklist', 'checklist.json',
  '--outputs', 'outputs.json'
]))
" | python3 -m json.tool
```

**Output:**
```json
{
  "checklist_name": "code_quality",
  "evaluation": {
    "total_outputs": 2,
    "total_passed": 1,
    "pass_rate": 50.0,
    "average_score": 83.3,
    "results": [
      {
        "output_id": "output_v1",
        "score": 100.0,
        "passed_all": true
      },
      {
        "output_id": "output_v2",
        "score": 66.7,
        "passed_all": false
      }
    ]
  }
}
```

## 4. Use in Python Code

```python
import sys
sys.path.insert(0, 'src')

from skill_auto_improver.checklist_evaluator import (
    ChecklistLoader, ChecklistEvaluator
)

# Load checklist
checklist = ChecklistLoader.load_from_file('checklist.json')

# Create evaluator
evaluator = ChecklistEvaluator(checklist)

# Evaluate outputs
outputs = {
    "version_1": {"q1_compiles": True, "q2_has_docstring": True},
    "version_2": {"q1_compiles": True, "q2_has_docstring": False},
}

report = evaluator.evaluate_all(outputs)

print(f"Average score: {report.average_score:.1f}%")
print(f"Pass rate: {report.pass_rate:.1f}%")
```

## 5. Custom Evaluator (Advanced)

For complex logic, pass a custom evaluator function:

```python
def evaluate_output(output: dict, question) -> bool:
    """Custom evaluation logic."""
    if question.id == "q1_compiles":
        # Check exit code
        return output.get("exit_code") == 0
    elif question.id == "q2_has_docstring":
        # Check for docstring
        return len(output.get("docstring", "")) > 20
    return False

evaluator = ChecklistEvaluator(checklist, evaluator_fn=evaluate_output)
report = evaluator.evaluate_all(outputs)
```

## 6. Hybrid Evaluation (Fixtures + Checklist)

Combine with golden fixtures:

```bash
python3 -c "
import sys
sys.path.insert(0, 'src')
from skill_auto_improver.cli import main
sys.exit(main([
  'evaluate-hybrid',
  '--skill-path', '.',
  '--fixtures', 'fixtures.json',
  '--checklist', 'checklist.json',
  '--outputs', 'outputs.json',
  '--require-both'  # Both gates must pass
]))
" | python3 -m json.tool
```

## Patterns

### Pattern: Field Exists

Check if a field exists in output:

```json
{
  "id": "has_field_response",
  "question": "Has response field?"
}
```

In output:
```json
{"has_field_response": "some value"}  // ✓ passes (truthy)
{"has_field_response": null}          // ✗ fails (falsy)
```

### Pattern: Field Non-Empty

Check if a field exists and is non-empty:

```json
{
  "id": "is_non_empty_description",
  "question": "Is description populated?"
}
```

In output:
```json
{"is_non_empty_description": "text"}  // ✓ passes (truthy)
{"is_non_empty_description": ""}      // ✗ fails (empty string)
{"is_non_empty_description": []}      // ✗ fails (empty array)
```

### Pattern: Direct Value

Simple boolean field:

```json
{
  "id": "q1_valid",
  "question": "Is output valid?"
}
```

In output:
```json
{"q1_valid": true}   // ✓ passes
{"q1_valid": false}  // ✗ fails
```

## Common Questions

**Q: How many questions should I have?**
A: 3-6 is ideal. Keep it focused.

**Q: Can I have optional questions?**
A: Yes! Use `"required": false`. They count toward score but aren't critical.

**Q: What's the difference from fixtures?**
A: 
- **Fixtures**: Exact structural matching (before/after equality)
- **Checklists**: Quality gates (question-based evaluation)

Use both together!

**Q: Can I use an LLM to evaluate?**
A: Yes! Implement a custom evaluator function that calls your LLM.

**Q: How do I integrate with safe-patch-trial?**
A: Use `create_checklist_evaluator_stage()` as your evaluate stage.

## Next Steps

- Read `CHECKLIST_MODE.md` for complete API docs
- Check `examples/checklist_example.py` for more examples
- Explore `examples/sample_checklist.json` and `examples/sample_outputs.json`
