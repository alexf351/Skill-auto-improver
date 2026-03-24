# Contributing to Skill Auto-Improver

Thank you for your interest in contributing! This guide explains how to develop, test, and submit improvements.

## Development Setup

### Prerequisites

- Python 3.9+
- Git
- Access to OpenClaw workspace

### Local Setup

```bash
# Clone and navigate to project
cd ~/.openclaw/workspace/skill-auto-improver

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate

# Install dependencies (if any)
pip install -r requirements.txt  # (currently no external deps)

# Verify installation
python -c "from skill_auto_improver import SkillAutoImprover; print('OK')"
```

## Architecture

Skill Auto-Improver follows a modular architecture:

```
src/skill_auto_improver/
├── loop.py                    # Core observe → inspect → amend → evaluate pipeline
├── operating_memory.py        # Structured memory for current + prior trial state
├── evaluator.py              # Golden fixture evaluation engine
├── proposer.py               # Amendment proposal generator
├── ab_evaluator.py           # A/B evaluation for regression detection
├── applier.py                # Applies proposed amendments to skills
├── shared_brain.py           # Multi-skill shared learning blocks
├── orchestrator.py           # Multi-skill coordination
├── nightly_orchestrator.py   # Cron job: nightly improvement trials
├── morning_summary_sender.py # Cron job: send summary to Telegram
├── nightly_backup.py         # Cron job: backup entire workspace
├── logger.py                 # Logging utilities
├── cli.py                    # Command-line interface
└── models.py                 # Data classes and schemas
```

## Testing

### Run All Tests

```bash
# From project root
pytest tests/ -v

# With coverage
pytest tests/ --cov=skill_auto_improver --cov-report=html
```

### Run Specific Tests

```bash
# Test a single module
pytest tests/test_loop.py -v

# Test a specific test class
pytest tests/test_orchestrator.py::MultiSkillOrchestratorTest -v

# Test a specific test method
pytest tests/test_shared_brain.py::SharedBrainTest::test_promotion_wisdom_recording -v
```

### Example Tests

Run any of the example scripts to verify functionality:

```bash
# Basic loop example
python examples/full_loop_with_proposals.py

# Multi-skill orchestration
python examples/multi_skill_orchestration_demo.py

# Real skills trial
python examples/real_skill_guarded_trial.py
```

## Code Style

### Standards

- **Language:** Python 3.9+ with full type hints
- **Style:** PEP 8 (enforced with flake8/black)
- **Docstrings:** Google-style on all public APIs
- **Comments:** Inline comments for non-obvious logic

### Example Function

```python
def propose_amendments(self, test_results: List[TestResult]) -> ProposalReport:
    """
    Generate structured patch proposals from failing test cases.

    Analyzes deltas between expected and actual outputs, then generates
    proposals for instruction changes, test cases, or reasoning hints.

    Args:
        test_results: List of test results with failures

    Returns:
        ProposalReport with all generated proposals grouped by type

    Raises:
        ValueError: If test_results is empty
    """
    if not test_results:
        raise ValueError("test_results cannot be empty")

    proposals = []
    for result in test_results:
        if result.status != "fail":
            continue

        # Generate instruction proposals first (highest impact)
        for proposal in self._generate_instruction_proposals(result):
            proposals.append(proposal)

    return ProposalReport(proposals=proposals)
```

## Workflow

### For New Features

1. **Design:** Create issue or discussion describing the feature
2. **Branch:** Create feature branch `feature/description`
3. **Implement:** Add code, tests, and documentation
4. **Test:** Run full test suite and examples
5. **Document:** Update README and relevant guides
6. **Submit:** Open pull request with description

### For Bug Fixes

1. **Report:** Document bug with reproduction steps
2. **Branch:** Create fix branch `fix/description`
3. **Test:** Write test that demonstrates the bug
4. **Fix:** Implement fix that passes test
5. **Verify:** Ensure no regressions in test suite
6. **Submit:** Open pull request with before/after

### For Documentation

1. **Update:** Edit markdown files or docstrings
2. **Review:** Check formatting and examples
3. **Test:** Verify code examples run correctly
4. **Submit:** Open pull request

## Testing Requirements

- ✅ All new code must have unit tests
- ✅ Tests should cover happy path + edge cases
- ✅ All existing tests must pass
- ✅ Code coverage should remain ≥90%
- ✅ Examples should demonstrate the new feature

## Documentation Requirements

- ✅ Public APIs must have docstrings
- ✅ Non-obvious logic needs inline comments
- ✅ New modules need README or guide
- ✅ Configuration options documented
- ✅ Usage examples provided

## Commit Messages

Use clear, descriptive commit messages:

```
feat: Add multi-skill orchestrator module
  - Implement MultiSkillOrchestrator for coordinating improvements
  - Add SkillTrialConfig for per-skill configuration
  - Add 15 unit tests with full coverage

fix: Handle missing SKILL.md files gracefully
  - Check for file existence before parsing
  - Log warning instead of raising exception
  - Add test case for missing file scenario

docs: Update MULTI_SKILL_GUIDE with new API examples
  - Add section on cross-skill learning
  - Include best practices for fixture reuse
  - Add troubleshooting guide

test: Increase test coverage for shared_brain module
  - Add tests for brain persistence
  - Add tests for concurrent access patterns
  - Verify state recovery from corrupted JSON
```

## Pull Request Process

1. **Ensure tests pass:**
   ```bash
   pytest tests/ -v --cov
   ```

2. **Update documentation:**
   - README if adding major features
   - Docstrings for API changes
   - ROADMAP if appropriate

3. **Write clear PR description:**
   - Problem: What issue are you solving?
   - Solution: How does your change fix it?
   - Testing: How did you verify it works?
   - Impact: Any breaking changes?

4. **Link related issues:**
   - Use `Fixes #123` to auto-close issues
   - Reference discussions in description

## Code Review Checklist

Before submitting:

- [ ] Code follows PEP 8 style guide
- [ ] All type hints are present
- [ ] Docstrings added for public APIs
- [ ] Unit tests cover new functionality
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] No breaking changes (or documented)
- [ ] Documentation updated
- [ ] Examples run without errors

## Common Tasks

### Add a New Evaluation Method

1. Extend `Evaluator` base class in `evaluator.py`
2. Implement required methods with type hints
3. Add unit tests in `tests/test_evaluator.py`
4. Document in `MULTI_SKILL_GUIDE.md`
5. Add example in `examples/`

### Add a New Proposal Type

1. Create proposal class in `models.py`
2. Add generation logic to `ProposalEngine` in `proposer.py`
3. Add tests in `tests/test_proposer.py`
4. Document in docstring with examples
5. Update proposal factory method

### Add Shared Brain Memory Block

1. Create new `MemoryBlock` subclass in `shared_brain.py`
2. Implement persistence (to_dict/from_dict)
3. Add query methods for retrieval
4. Add tests in `tests/test_shared_brain.py`
5. Document in `MULTI_SKILL_GUIDE.md`

### Add Cron Job

1. Create new module in `src/skill_auto_improver/`
2. Implement runner class with `run()` method
3. Add logging via `SkillAutoImproverLogger`
4. Create example/test script
5. Document in `CRON_SETUP.md`
6. Add to cron scheduler configuration

## Performance Considerations

- **Memory:** Keep operating memory bounded (default: last 100 trials)
- **Disk:** Archive old runs periodically
- **API Calls:** Batch Telegram sends when possible
- **File I/O:** Use buffered writes for large logs
- **JSON Parsing:** Cache parsed fixtures during trial

## Security

- 🔒 Never commit API keys or tokens
- 🔒 Use environment variables for credentials
- 🔒 Validate file paths to prevent traversal
- 🔒 Sanitize Telegram messages
- 🔒 Restrict backup file permissions (chmod 600)

## Questions or Issues?

- **Documentation:** See README.md and guides
- **Bug Reports:** Use GitHub issues with reproduction steps
- **Discussions:** Open a discussion for design questions
- **Security:** Contact maintainers privately

## License

By contributing, you agree that your contributions are licensed under the MIT License (see LICENSE file).

---

Thank you for helping improve Skill Auto-Improver! 🎯
