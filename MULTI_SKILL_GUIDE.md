# Multi-Skill Orchestration Guide

This document explains how to use the multi-skill orchestration layer with the shared brain for coordinating improvements across multiple skills.

## Overview

The multi-skill system enables:

1. **Shared Brain** - Structured memory blocks that capture insights across all skills
2. **Cross-Skill Learning** - Patterns learned from one skill inform improvements in others
3. **Promotion Wisdom** - Understanding why certain patches succeed (and which skills they succeeded in)
4. **Regression Prevention** - Shared awareness of common failure modes
5. **Unified Orchestration** - Run improvement trials on multiple skills in sequence with coordinated learning

## Architecture

### Shared Brain Memory Blocks

The `SharedBrain` class maintains five structured memory blocks:

#### 1. Core Directives (`core_directives.json`)

System-wide operational rules that apply across skills.

**Structure:**
```python
@dataclass
class CoreDirective:
    id: str  # e.g. "cd_001_min_confidence"
    title: str
    description: str
    applies_to: list[str]  # skill patterns: ["weather*"], ["*"] for all
    auto_apply: bool  # enforce automatically?
    example: Optional[str]
```

**Default Directives:**
- `cd_001_min_confidence`: Never auto-apply proposals below 0.80 confidence
- `cd_002_test_case_first`: Require test_case proposals for historically broken fixtures
- `cd_003_no_churn`: Reject patches exceeding change budget (>10 targets, >100 lines)

**Usage:**
```python
brain = SharedBrain("./brain")
directives = brain.get_directives_for_skill("weather-brief")
# Returns: [CoreDirective(...), CoreDirective(...), ...]
```

#### 2. Promotion Wisdom (`promotion_wisdom.json`)

Why successful patches got accepted, cross-skill.

**Structure:**
```python
@dataclass
class PromotionWisdom:
    id: str
    fixture_name: str  # e.g. "formal_greeting_test"
    description: str
    acceptance_reason: str  # why it was accepted
    skills_successful: list[str]  # ["weather-brief", "kiro"]
    proposal_type_sequence: list[str]  # ["test_case", "instruction"]
    confidence_floor: float  # 0.8-1.0
    confidence: float  # actual confidence
    shared_lessons: list[str]  # reusable tips
    promotion_count: int  # how many times promoted?
```

**Usage:**
```python
# Record a successful promotion
wisdom = brain.record_promotion(
    fixture_name="formal_greeting_test",
    skill_name="weather-brief",
    proposal_types=["test_case", "instruction"],
    reason="100% recovery, zero regressions",
    confidence=0.92,
    shared_lessons=["Always pair instruction with test for greeting tests"],
)

# Retrieve wisdom for a fixture
wisdom_entries = brain.get_promotion_wisdom_for_fixture("greeting_test")
```

**Cross-Skill Benefit:** When a new skill tries the same fixture pattern, the proposer can:
- Boost confidence based on successful cross-skill history
- Suggest the proven proposal sequence
- Apply shared lessons from other skills

#### 3. Regression Patterns (`regression_patterns.json`)

Common failure modes observed across skills.

**Structure:**
```python
@dataclass
class RegressionPattern:
    id: str
    pattern_name: str
    description: str
    triggers: list[str]  # e.g. ["instruction_only_proposal"]
    fix_strategy: str
    severity: str  # "warning" | "critical"
    observed_in_skills: list[str]  # which skills hit this?
    prevention_rule: Optional[str]
    occurrence_count: int  # how many times observed?
    prevention_success_rate: float
```

**Usage:**
```python
# Record a regression
pattern = brain.record_regression(
    pattern_name="instruction_only_breaks_tests",
    skill_name="kiro",
    trigger="instruction proposal without test_case",
    fix_strategy="Require test_case proposals for risky fixtures",
    severity="critical",
)

# Get patterns specific to a skill
patterns = brain.get_regression_patterns_for_skill("kiro")
```

**Cross-Skill Benefit:** When a new skill is being improved:
- Pre-load known regression patterns
- Apply prevention rules automatically
- Alert operators to patterns already seen elsewhere

#### 4. Fixture Library (`fixture_library.json`)

Shared fixture patterns that work well across skills.

**Structure:**
```python
@dataclass
class FixtureLibraryEntry:
    id: str
    fixture_pattern_name: str
    description: str
    fixture_template: dict[str, Any]  # reusable structure
    expected_behavior: str
    successful_skills: list[str]
    anti_patterns: list[str]
    adaptability_notes: str
```

**Usage:**
```python
# Add a successful fixture to the shared library
entry = brain.add_fixture_to_library(
    fixture_pattern_name="formal_greeting",
    fixture_template={
        "name": "greeting_test",
        "input_data": {"name": "Alice"},
        "expected_output": {"greeting": "Hello, Alice!"},
    },
    expected_behavior="Greet with formal salutation",
    successful_skills=["weather-brief", "kiro"],
)

# Find similar fixtures in the library
similar = brain.get_similar_fixtures("greeting_test", limit=5)
```

**Cross-Skill Benefit:** New skills can:
- Reuse proven fixture patterns from other skills
- Adapt fixtures that are similar to their needs
- Build on established best practices

#### 5. Skill Mastery (`skill_mastery.json`)

Per-skill learned insights and metrics.

**Structure:**
```python
@dataclass
class SkillMastery:
    skill_name: str
    skill_type: str  # "weather", "kiro", "research"
    total_trials: int
    successful_promotions: int
    regression_incidents: int
    average_proposal_confidence: float
    most_effective_proposal_types: list[str]
    fixture_mastery: dict[str, dict[str, Any]]  # per-fixture insights
    common_issues: list[str]
```

**Usage:**
```python
# Get or create mastery record
mastery = brain.get_or_create_skill_mastery("kiro", skill_type="mobile_app")

# Update with trial results
brain.update_skill_mastery(
    "kiro",
    total_trials=mastery.total_trials + 1,
    successful_promotions=mastery.successful_promotions + 1,
    most_effective_proposal_types=["test_case", "instruction"],
)

# Get comprehensive skill summary
summary = brain.summarize_for_skill("kiro")
```

**Cross-Skill Benefit:** Before improving a skill:
- Check what has worked well for similar skills
- Load proven proposal types and patterns
- Understand skill-specific challenges

## Multi-Skill Orchestrator

The `MultiSkillOrchestrator` coordinates improvements across multiple skills using the shared brain.

### Basic Usage

```python
from skill_auto_improver.orchestrator import MultiSkillOrchestrator, SkillTrialConfig

# Initialize orchestrator with shared brain
orchestrator = MultiSkillOrchestrator(brain_dir="./.skill-auto-improver/brain")

# Define trials for multiple skills
configs = [
    SkillTrialConfig(
        skill_path="/path/to/weather-brief",
        skill_name="weather-brief",
        skill_type="forecast",
        fixtures_path="/path/to/fixtures.json",
        min_confidence=0.85,
    ),
    SkillTrialConfig(
        skill_path="/path/to/kiro",
        skill_name="kiro",
        skill_type="mobile_app",
        fixtures_path="/path/to/fixtures.json",
        min_confidence=0.80,
    ),
]

# Run orchestration (improves multiple skills sequentially)
run = orchestrator.run_orchestration(
    skill_configs=configs,
    logs_dir="./orchestration-logs",
)

print(f"Run ID: {run.run_id}")
print(f"Successful trials: {run.successful_trials}/{run.total_skills}")
print(f"Promotions accepted: {run.promotions_accepted}")
```

### Orchestration Run Output

```python
@dataclass
class OrchestrationRun:
    run_id: str
    started_at: str
    finished_at: Optional[str]
    
    # Per-skill results
    skill_trials: dict[str, RunTrace]
    skill_outcomes: dict[str, dict[str, Any]]
    
    # Cross-skill insights
    promotions_recorded: list[str]
    regressions_recorded: list[str]
    fixtures_added_to_library: list[str]
    
    # Metrics
    total_skills: int
    successful_trials: int
    rolled_back_trials: int
    promotions_accepted: int
    regressions_prevented: int
```

### Pre-Trial Context

Get brain state relevant to a specific skill before running its trial:

```python
context = orchestrator.get_skill_context_for_trial("kiro")
# Returns:
# {
#   "applicable_directives": [...],
#   "regression_patterns_to_watch": [...],
#   "similar_fixtures_in_library": [...],
#   "skill_mastery": {...},
# }
```

### Brain Summaries

Check the state of the shared brain:

```python
summary = orchestrator.get_brain_summary()
# Returns:
# {
#   "core_directives": 3,
#   "promotion_wisdom_entries": 12,
#   "regression_patterns": 8,
#   "fixture_library_entries": 25,
#   "skills_tracked": 5,
#   "total_successful_trials_recorded": 47,
#   "total_regressions_prevented": 23,
# }
```

## Cross-Skill Learning Patterns

### Pattern 1: Promotion Wisdom Cascading

When a fixture pattern succeeds in one skill, the orchestrator can:

1. **Record the Success**
   ```python
   brain.record_promotion(
       fixture_name="greeting_format",
       skill_name="skill_a",
       proposal_types=["test_case", "instruction"],
       reason="100% recovery",
       confidence=0.92,
   )
   ```

2. **Retrieve for Another Skill**
   ```python
   wisdom = brain.get_promotion_wisdom_for_fixture("greeting_format")
   # wisdom.skills_successful = ["skill_a", ...]
   # wisdom.proposal_type_sequence = ["test_case", "instruction"]
   ```

3. **Apply to New Skill**
   - Proposer sees proven sequence and boosts confidence
   - Applies shared lessons automatically
   - Suggests test_case first for this fixture

### Pattern 2: Regression Pattern Prevention

When a regression is observed:

1. **Record the Pattern**
   ```python
   brain.record_regression(
       pattern_name="instruction_without_test",
       skill_name="skill_a",
       trigger="proposal lacks test_case",
       fix_strategy="Require test_case for risky fixtures",
   )
   ```

2. **Prevent in Other Skills**
   ```python
   patterns = brain.get_regression_patterns_for_skill("skill_b")
   # Shows that "instruction_without_test" affects multiple skills
   # Applies prevention rule automatically
   ```

### Pattern 3: Fixture Library Reuse

When a fixture pattern works well:

1. **Add to Library**
   ```python
   brain.add_fixture_to_library(
       fixture_pattern_name="greeting_formal",
       fixture_template={...},
       expected_behavior="Formal greeting",
       successful_skills=["skill_a", "skill_b"],
   )
   ```

2. **Reuse in New Skill**
   ```python
   similar = brain.get_similar_fixtures("greeting_test")
   # Returns pre-built templates from other successful skills
   ```

### Pattern 4: Skill Mastery Insights

Track what works best for each skill type:

1. **Build Mastery**
   ```python
   brain.update_skill_mastery(
       "kiro",
       total_trials=10,
       successful_promotions=8,
       most_effective_proposal_types=["test_case", "instruction"],
       average_proposal_confidence=0.89,
   )
   ```

2. **Apply to Similar Skills**
   ```python
   mastery = brain.get_skill_mastery("kiro")
   # Other mobile_app skills benefit from:
   # - Same proposal type preferences
   # - Similar confidence floors
   # - Known fixture patterns
   ```

## CLI Integration (Future)

```bash
# Run multi-skill orchestration
python3 -m skill_auto_improver.cli orchestrate \
  --config orchestration.json \
  --logs-dir ./runs

# Check brain state
python3 -m skill_auto_improver.cli brain-summary \
  --brain-dir ./.skill-auto-improver/brain

# Get pre-trial context for a skill
python3 -m skill_auto_improver.cli get-skill-context \
  --skill-name kiro \
  --brain-dir ./.skill-auto-improver/brain
```

## Example: Weather + Kiro Multi-Skill Run

```python
from skill_auto_improver.orchestrator import MultiSkillOrchestrator, SkillTrialConfig

# Initialize
orch = MultiSkillOrchestrator(brain_dir="./.skill-auto-improver/brain")

# Run initial weather-brief trial
weather_run = orch.run_orchestration([
    SkillTrialConfig(
        skill_path="./skills/weather-brief",
        skill_name="weather-brief",
        skill_type="forecast",
        fixtures_path="./fixtures/weather.json",
        min_confidence=0.85,
    ),
])

print(f"Weather trial: {weather_run.successful_trials} successful")

# Weather trial recorded promotions and regressions to brain
# Now Kiro can benefit from weather's learnings

kiro_run = orch.run_orchestration([
    SkillTrialConfig(
        skill_path="./skills/kiro",
        skill_name="kiro",
        skill_type="mobile_app",
        fixtures_path="./fixtures/kiro.json",
        min_confidence=0.85,
    ),
])

# Kiro can reuse:
# - Promotion wisdom from greeting fixtures (weather also has them)
# - Prevention rules for regressions (e.g., instruction_without_test)
# - Fixture library patterns from weather

print(f"Kiro trial: {kiro_run.successful_trials} successful")
print(f"Brain now has: {orch.get_brain_summary()}")
```

## Best Practices

1. **Start with Known-Good Fixtures**
   - Let the first skill succeed thoroughly
   - Build promotion wisdom and fixture library
   - Other skills benefit from proven patterns

2. **Use Shared Lessons**
   - When recording promotion wisdom, include lessons for other skills
   - Capture what made the change succeed
   - Enable cross-skill transfer

3. **Watch Regression Patterns**
   - Review `regression_patterns.json` periodically
   - Update prevention rules as patterns emerge
   - Share fixes across skills quickly

4. **Maintain Directives**
   - Keep core directives aligned with system goals
   - Update patterns as needed
   - Use `applies_to` to target specific skill types

5. **Track Skill Mastery**
   - Update mastery records after each trial
   - Monitor which proposal types work best
   - Identify common issues early

## Data Persistence

All five memory blocks persist to JSON files in the brain directory:

```
.skill-auto-improver/brain/
├── core_directives.json          # System-wide operational rules
├── promotion_wisdom.json         # Why patches succeeded
├── regression_patterns.json      # Common failure modes
├── fixture_library.json          # Reusable fixture patterns
└── skill_mastery.json            # Per-skill learned insights
```

Each file is human-readable and can be manually reviewed/edited.

## Testing

Run the test suite:

```bash
cd skill-auto-improver
PYTHONPATH=./src python3 -m unittest tests.test_shared_brain tests.test_orchestrator -v
```

Expected: 37 tests passing (22 brain + 15 orchestrator).

## Next Steps

1. **Integration with Proposer** - Pass brain context to proposal generation
2. **Memory-Driven Proposal Ranking** - Use promotion wisdom to rank proposals
3. **Cross-Skill Fixture Suggestions** - Recommend library fixtures for new skills
4. **Unified Operator Dashboard** - CLI for brain state, cross-skill metrics
5. **Automated Promotion Rules** - Apply learned rules without manual intervention
