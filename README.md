# Skill Auto-Improver MVP

A practical MVP for autonomously improving user-built skills via structured observe → inspect → amend → evaluate loops.

## Goal

Enable continuous improvement of AgentSkills by:
1. **Observing** actual skill behavior (logs, outputs, errors)
2. **Inspecting** failure patterns and root causes
3. **Amending** the skill (proposing patches)
4. **Evaluating** against golden test cases to confirm improvement

With built-in **rollback safety** and **version history**.

## What's Shipped

### ✅ Multi-Skill Orchestration + Shared Brain (2026-03-24)

**Files:** 
- `src/skill_auto_improver/shared_brain.py` — Structured memory for cross-skill learning
- `src/skill_auto_improver/orchestrator.py` — Coordinate improvements across multiple skills

**Shared Brain Memory Blocks:**
- **Core Directives**: System-wide operational rules (e.g., "min confidence 0.80", "test_case first for risky fixtures")
- **Promotion Wisdom**: Why patches succeeded, across which skills, with learned lessons
- **Regression Patterns**: Common failure modes observed in multiple skills + prevention strategies
- **Fixture Library**: Reusable fixture patterns with successful skill history
- **Skill Mastery**: Per-skill insights (most effective proposal types, common issues, trial history)

**Orchestrator Features:**
- `MultiSkillOrchestrator`: Run improvement trials on multiple skills sequentially
- `SkillTrialConfig`: Define trial parameters for each skill
- `OrchestrationRun`: Captures results, metrics, and cross-skill insights
- Per-skill context generation from shared brain (directives, patterns, library)
- Persistent orchestration logs with full traceability

**Cross-Skill Learning:**
- Promotion wisdom cascading: Success in one skill informs proposals in others
- Regression prevention: Patterns learned from one skill prevent regressions in others
- Fixture library reuse: Proven patterns from successful skills bootstrap new skills
- Skill mastery tracking: Understand what works best for each skill type

**Tests:** 22 unit tests for shared brain, 15 unit tests for orchestrator (all passing)

**Documentation:** `MULTI_SKILL_GUIDE.md` with complete API, examples, and best practices

## What's Shipped

### ✅ Baseline: Observe → Inspect → Amend → Evaluate Loop (2026-03-14)

**File:** `src/skill_auto_improver/loop.py`

- `SkillAutoImprover`: Core pipeline runner with four pluggable stages
- `RunTrace`: Structured trace schema (skill_path, status, steps, metadata)
- Error short-circuit: stops at first failure, logs everything
- `stage_order` parameter for custom pipeline orderings (e.g., evaluate before amend)

**Tests:** 5 unit tests covering happy path, failure handling, and noop smoke run

### ✅ Golden-Output Evaluator (2026-03-15)

**File:** `src/skill_auto_improver/evaluator.py`

Allows skills to be evaluated against golden test fixtures:

- `GoldenFixture`: Single test case with input + expected output
- `GoldenFixtureLoader`: Load from JSON or dict
- `GoldenEvaluator`: Score actual outputs against fixtures
  - Single snapshot evaluation (`evaluate_snapshot`)
  - Batch evaluation (`evaluate_all`)
  - Automatic delta computation (shows what changed)
- `EvaluationReport`: Summary with pass_rate and per-fixture results
- `create_golden_evaluator_stage()`: Factory function to drop evaluator into the loop

**Tests:** 11 unit tests covering fixture loading, pass/fail scoring, delta computation

### ✅ Amendment Proposal Engine (2026-03-16)

**File:** `src/skill_auto_improver/proposer.py`

Generates structured patch proposals from failing test cases:

- `ProposalEngine`: Analyzes `TestResult` deltas and generates proposals
- `PatchProposal`: Single actionable suggestion (type, severity, confidence)
- `ProposalReport`: Summary with all proposals grouped/indexed
- Three proposal types:
  - **Instruction**: Rewrite guidance in SKILL.md
  - **Test case**: Add regression tests to prevent repeats
  - **Reasoning**: Diagnostic hints (root cause hypothesis)
- `create_amendment_proposal_stage()`: Factory for amend stage
- Severity escalation: "warning" (1 mismatch) → "critical" (2+ mismatches)
- Confidence scoring: 0.8–0.9 depending on proposal type

**Tests:** 10 unit tests covering all proposal types, confidence levels, severity escalation, and full pipeline integration

### ✅ A/B Evaluation Runner (2026-03-16)

**File:** `src/skill_auto_improver/ab_evaluator.py`

Compares before/after evaluation reports for regression detection and improvement metrics:

- `ABEvaluator`: Compare two `EvaluationReport` objects
- `ABComparison`: Per-fixture comparison with status (recovered, regressed, stable_pass, stable_fail)
- `ABReport`: Summary with pass_rate_delta, recovered/regressed counts, is_safe flag
- `create_ab_evaluation_stage()`: Factory for drop-in loop integration
- Union behavior: tracks all fixtures from before and after (detects new test additions)

**Tests:** 9 unit tests covering recovered, regressions, mixed outcomes, edge cases, serialization

### ✅ Patch Apply/Plan Flow (2026-03-17)

**File:** `src/skill_auto_improver/applier.py`

Turns generated proposals into reviewable file changes with lightweight safety rails:

- `SkillPatchApplier`: Applies accepted proposals to a target skill directory
- `ApplyReport`: Structured summary of applied vs skipped changes
- `create_patch_apply_stage()`: Factory for loop integration
- Supports:
  - Instruction proposal application to `SKILL.md`
  - Regression fixture appends to `golden-fixtures.json`
  - Dry-run planning (`mode="plan"`) with zero file mutation
  - Backup snapshots in `.skill-auto-improver/backups/` before mutating existing files
  - Duplicate fixture detection and default skip behavior for unsupported proposal types

**Tests:** 6 unit/integration tests covering backups, dry-run safety, duplicate detection, and loop-stage planning

### ✅ Guarded Patch Trial + Auto-Rollback (2026-03-18)

**File:** `src/skill_auto_improver/loop.py`

Wires the missing end-to-end safety path for real amendment trials:

- `create_safe_patch_trial_stage()`: baseline eval → apply proposals → after eval → A/B comparison
- Auto-reuses `before_eval` from context when already available, otherwise computes it fresh
- Automatically restores backups when a candidate patch introduces regressions
- Returns a single structured result containing `before_eval`, `apply`, `after_eval`, `ab`, and rollback status

**Tests:** 2 end-to-end loop tests covering accepted improvements and automatic rollback on regression

### ✅ Trace Metadata Summaries (2026-03-18)

**File:** `src/skill_auto_improver/loop.py`

Makes run logs easier to audit by lifting key outcomes into `RunTrace.metadata`:

- Persists compact evaluation totals (`total`, `passed`, `failed`, `pass_rate`) when golden evaluation runs
- Persists guarded patch-trial summary fields (`accepted`, `rolled_back`, `applied_count`, `regressed_count`, `pass_rate_delta`, etc.)
- Keeps full step payloads intact while making common operator checks one lookup away in trace JSON

**Tests:** 2 loop tests covering persisted evaluation metadata and persisted patch-trial metadata

### ✅ Backup IDs + Diff Summaries in Apply Reports (2026-03-19)

**Files:** `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/loop.py`

Upgrades patch-trial auditability so operators can see exactly what changed without opening full files first:

- Adds `backup_id` to each applied change when a snapshot exists
- Adds compact `diff_summary` payloads (`added_lines`, `removed_lines`, preview lines)
- Lifts backup IDs + diff summaries into `RunTrace.metadata["patch_trial"]` for fast log review
- Preserves plan-mode previews, so dry runs now show intended diffs too

**Tests:** Expanded apply + loop assertions covering backup identifiers and diff summaries

### ✅ Persistent Operating-Memory Scaffold (2026-03-20)

**Files:** `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/cli.py`

Adds a reusable doctrine/memory layer for target skills so improvement compounds over time:

- `doctrine.md` — durable execution policy
- `lessons.md` — reusable corrections and learned rules
- `todo.md` — active planning/tracking surface
- `gotchas.md` — recurring failure modes
- `verification.md` — definition of done / proof standard
- `data/preferences.json` — normalized reusable preferences
- `data/run-history.jsonl` — structured run log
- `data/feedback.log` — append-only user correction log

CLI:
```bash
python3 -m skill_auto_improver.cli scaffold-memory --skill-path /path/to/skill
```

### ✅ Operating-Memory Trial Logging (2026-03-21)

**Files:** `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/loop.py`

Makes the scaffolded memory layer actually participate in real improvement runs:

- Guarded patch trials now auto-bootstrap operating-memory if missing
- Every safe patch trial appends a structured entry to `data/run-history.jsonl`
- Trial outcomes now update operator-facing memory surfaces:
  - `todo.md` review notes
  - `verification.md` proof blocks
  - `lessons.md` when a patch safely recovers failures
  - `gotchas.md` when a patch regresses and rolls back
- Trial output includes an `operating_memory` block with scaffold + history details

### ✅ Memory-Biased Proposals + Guarded Acceptance + Backup Ergonomics (2026-03-21)

**Files:** `src/skill_auto_improver/proposer.py`, `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/loop.py`, `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/cli.py`

Turns operating memory into an actual control surface instead of a passive log:

- Proposal generation now reads lessons/gotchas/preferences/run-history and injects memory hints into proposal descriptions/content
- Repeatedly problematic fixtures get elevated severity/confidence and proposal ordering can follow memory preferences
- Safe trials now merge policy from memory (`min_confidence`, severity allowlist, rollback default) before apply
- Guarded trials reject no-op / no-improvement runs instead of calling every safe diff an acceptance
- Backup ergonomics improved with:
  - backup-id resolution (`restore-backup --backup <id>`)
  - target-name filtering for inspection/restore
  - `backup-history` CLI combining snapshot inventory + recent operating-memory trial history
  - backup summaries embedded in trial output/trace metadata

### ✅ Smarter Section Updates + Memory-Driven Change Budgets (2026-03-23)

**Files:** `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/loop.py`, `tests/test_applier.py`, `tests/test_loop.py`

Deepens full skill-system mutation safety in two practical ways:

- Instruction/artifact apply logic now updates an existing fixture-specific markdown block when possible instead of blindly appending duplicate sections
- Dedicated artifact files can be refreshed in place when they already contain the target heading
- Operating-memory policy now supports change-budget controls:
  - `max_changed_targets`
  - `max_added_lines`
  - optional fixture-level overrides for both
- Safe trials now compute a `change_guard` from actual applied diffs and reject/rollback patches that exceed memory-defined churn budgets
- Rollback flow now also removes newly created files when a rejected trial had no backup snapshot to restore
- Trial output and trace metadata now expose `change_guard` alongside normal A/B + promotion guard details

### ✅ Promotion Memory + Promoted-Baseline Guardrails (2026-03-23)

**Files:** `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/loop.py`, `tests/test_operating_memory.py`, `tests/test_loop.py`

Deepens acceptance/rollback logic with explicit promoted-state memory instead of treating each trial as isolated:

- Operating-memory scaffold now creates `data/promotion.json`
- Accepted, non-rolled-back trials now snapshot the promoted baseline (`before_eval`, `after_eval`, AB summary, apply details, acceptance reason)
- Safe patch trials now compute a `promotion_guard` alongside normal A/B safety checks
- Promotion guardrails now compare against both the latest promoted snapshot and a configurable promotion-history window (`promotion_history_window`, `min_promotions_for_fixture_guard`)
- When `protect_promoted_fixtures` is enabled, trials that break fixtures from the last promoted baseline are rejected and rolled back with a distinct `promoted baseline regression` reason
- When historically stable fixtures re-break across multiple promoted runs, trials can now be rejected/rolled back with a distinct `promotion history regression` reason
- Trial output and trace metadata now include both `promotion_guard` and promotion-state details for downstream tooling

### ✅ Fixture-Aware Operating Memory Profiles (2026-03-21)

**Files:** `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/proposer.py`

Pushes operating memory one step further so proposal behavior can sharpen at the fixture level instead of only globally:

- `lessons.md` and `gotchas.md` are now parsed into structured entries, not just flat bullet strings
- `load_context()` now emits `proposal_hints.fixture_profiles[fixture_name]` with:
  - learned lessons
  - gotchas / regression markers
  - per-fixture history counters
  - per-fixture boost/avoid terms
  - per-fixture preferred proposal types
  - optional per-fixture policy overrides
- `data/preferences.json` now supports:
  ```json
  {
    "proposal": {
      "fixture_policies": {
        "greeting_test": {
          "boost_terms": ["keep salutations formal"],
          "avoid_terms": ["never say hey there"],
          "prefer_types": ["instruction"],
          "min_confidence": 0.95,
          "accepted_severities": ["critical"]
        }
      }
    }
  }
  ```
- Proposal generation now uses those fixture profiles to:
  - lift confidence toward fixture-specific floors
  - escalate severity for risky fixtures
  - surface sharper memory hints in descriptions/content
  - sort regression-prone fixtures ahead of lower-risk work

### ✅ Fixture-Level Policy Gates in Apply/Trial (2026-03-21)

**Files:** `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/loop.py`, `tests/test_applier.py`, `tests/test_loop.py`, `tests/test_cli.py`

Closes the gap between fixture-aware proposal shaping and actual guarded write decisions:

- `SkillPatchApplier.apply()` now accepts `fixture_policies` and enforces per-fixture overrides for:
  - `min_confidence`
  - `accepted_severities`
- Guarded patch trials now pass merged operating-memory fixture policy into apply, so a risky fixture can demand stricter acceptance than the global CLI defaults
- This means fixture-specific memory can now actively prevent writes, not just influence proposal ordering/text
- Added coverage proving:
  - fixture-level confidence floors block otherwise-allowed proposals
  - fixture-level severity policies override more permissive global settings
  - CLI trial runs honor fixture-level memory policy when no stricter CLI threshold is set

### ✅ Promotion-Aware Proposal Ranking + Full-Artifact Support (2026-03-23)

**Files:** `src/skill_auto_improver/proposer.py`, `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/operating_memory.py`, `src/skill_auto_improver/loop.py`, `tests/test_proposer.py`, `tests/test_applier.py`, `tests/test_loop.py`

Pushes memory-aware behavior further upstream into both proposal ordering and auto-apply policy, while expanding writes beyond `SKILL.md`:

- `OperatingMemory.load_context()` now emits `proposal_hints.promotion_profiles[fixture_name]` so proposer/applier logic can see historically protected fixtures, promoted pass counts, and required companion proposal types
- Proposal ranking now treats historically protected fixtures differently:
  - boosts `test_case` and `artifact` proposals ahead of broad instruction edits
  - exposes promotion-aware bias details in proposal payloads
  - can emit `artifact` proposals targeting supporting skill files like `references/auto-improver/<fixture>.md`
- `SkillPatchApplier.apply()` now supports `artifact` proposals for relative in-skill files, with backups/diff previews for existing targets
- Fixture policy can now require companion proposal types (e.g. `test_case`) before auto-apply, closing the loop from promotion history → proposal ranking → guarded acceptance
- Guarded patch trials can auto-derive that policy for historically protected fixtures when `require_test_case_for_protected_fixtures` is enabled
- Added coverage proving:
  - historically protected fixtures reorder proposal types toward safer/test-backed changes
  - non-`SKILL.md` supporting artifacts are created successfully
  - protected fixtures can block instruction-only auto-apply until a regression test accompanies the change

### ✅ Structure-Aware Artifact Targeting (2026-03-23)

**Files:** `src/skill_auto_improver/proposer.py`, `src/skill_auto_improver/loop.py`, `tests/test_proposer.py`, `tests/test_applier.py`, `tests/test_loop.py`

Makes artifact generation smarter by inspecting the target skill layout before deciding what companion asset to emit:

- Proposer now inspects the target skill folder and records a `skill_profile` in `memory_context`
- Artifact proposals no longer default blindly to `references/auto-improver/...`
- Current targeting logic:
  - prefer `references/auto-improver/<fixture>.md` when the skill already uses `references/`
  - prefer `docs/auto-improver/<fixture>.md` when the skill uses `docs/`
  - prefer checklist-style artifacts under `checklists/auto-improver/<fixture>.md` when the skill uses `checklists/`
  - fall back to `references/auto-improver/<fixture>.md` when no supporting-asset structure exists yet
- Artifact payloads now include:
  - `structure_reason`
  - embedded `skill_profile`
  - structure-specific `format` (`markdown_append` vs `markdown_checklist`)
- Added coverage proving:
  - docs-first skills get docs-targeted artifacts
  - checklist-oriented skills get checklist-formatted artifacts
  - amendment stage threads structure context end-to-end into generated proposals

### ✅ Command-Probe Evaluator Hooks for Real Skill Trials (2026-03-22)

**Files:** `src/skill_auto_improver/cli.py`, `tests/test_cli.py`

Expands guarded trial runs beyond static file-content checks so golden fixtures can execute lightweight real skill probes:

- Fixtures may now declare `input_data.command` as a string-list command, executed inside the target skill folder
- Command fixtures can assert against:
  - `exit_code`
  - `stdout_contains`
  - `stdout_not_contains`
  - `stderr_contains`
  - `stderr_not_contains`
- File-content probes and command probes can be mixed in the same fixture set via a shared `evaluate_skill_fixtures()` dispatcher
- Added CLI coverage proving:
  - direct command-probe evaluation works
  - guarded `trial` runs can recover a failing command-based fixture and keep the patch only when the probe turns green

### ✅ Proposal Acceptance Gates (2026-03-20)

**Files:** `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/loop.py`, `src/skill_auto_improver/cli.py`

Adds explicit operator policy controls before auto-applying generated proposals:

- `min_confidence` threshold blocks low-confidence proposals from apply/trial flows
- `accepted_severities` allowlist blocks proposal severities outside the operator policy
- `trial` CLI now accepts:
  - `--min-confidence 0.90`
  - `--accepted-severities warning critical`
- Skipped proposals remain visible in the apply report with a concrete reason

### ✅ Operator-Facing Backup Inspection Helper (2026-03-20)

**Files:** `src/skill_auto_improver/applier.py`, `src/skill_auto_improver/cli.py`

Makes backup snapshots reviewable before restore:

- `inspect_backups()` returns backup metadata plus a compact diff preview against the current live file
- New CLI commands:
  ```bash
  python3 -m skill_auto_improver.cli inspect-backups --skill-path /path/to/skill --limit 5
  python3 -m skill_auto_improver.cli restore-latest-backup --skill-path /path/to/skill --target-name SKILL.md
  ```
- Operators can now see which snapshot is relevant before triggering restore logic, or fast-revert the newest snapshot for a single target file

### ✅ Trace Logging + Trace-Aware Observe/Inspect (2026-03-23)

**Files:** `src/skill_auto_improver/logger.py`, `src/skill_auto_improver/loop.py`

- `TraceLogger`: Write `RunTrace` objects as JSON to timestamped files
- `load_traces()`: Load recent trace JSON artifacts for analysis
- `summarize_traces()`: Reduce trace history into operator/agent-friendly metrics
- `create_recent_run_observer_stage()`: Turn recent trial history into actionable observe-stage signals
- `create_trace_inspect_stage()`: Convert repeated rollback / no-apply / promoted-regression patterns into concrete priorities for the next amendment pass
- One file per run: `<run_id>.json`

### ✅ Real Skill Demo for Trace-Aware Guarded Trials (2026-03-23)

**Files:** `examples/real_skill_guarded_trial.py`, `examples/real_skill_demo/*`, `tests/test_examples.py`

Adds the missing concrete operator demo against a real skill-shaped folder instead of only unit-level mocked flows:

- `examples/real_skill_demo/skill/` contains a minimal `SKILL.md` plus `check_skill.py` runtime probe
- Demo golden fixtures use `input_data.command`, so the example validates a real command-probe loop
- `proposals-safe.json` demonstrates a recovery that gets accepted and promoted
- `proposals-regression.json` demonstrates a follow-up patch that gets rolled back because it breaks the promoted baseline
- `examples/real_skill_guarded_trial.py` also shows how to run trace-aware observe/inspect summaries between guarded trials
- `tests/test_examples.py` proves the example actually preserves the accepted skill state after rollback

## Quick Start

### Basic Evaluation

```python
from skill_auto_improver.evaluator import GoldenFixture, GoldenEvaluator

fixtures = [
    GoldenFixture(
        name="test_greeting",
        input_data={"name": "Alice"},
        expected_output={"greeting": "Hello, Alice!"},
    ),
]

evaluator = GoldenEvaluator(fixtures)
result = evaluator.evaluate_snapshot({"greeting": "Hello, Alice!"})
print(result.passed)  # True
```

### Full Loop with Proposals

```python
from skill_auto_improver.loop import (
    SkillAutoImprover,
    create_recent_run_observer_stage,
    create_trace_inspect_stage,
    create_golden_evaluator_stage,
    create_amendment_proposal_stage,
    create_patch_apply_stage,
)
from skill_auto_improver.evaluator import GoldenFixture

fixtures = [
    GoldenFixture(
        name="greeting_test",
        input_data={"name": "Alice"},
        expected_output={"greeting": "Hello, Alice!"},
    ),
]

improver = SkillAutoImprover(
    observe=create_recent_run_observer_stage("./runs", limit=5),
    inspect=create_trace_inspect_stage(),
    evaluate=create_golden_evaluator_stage(fixtures),
    amend=create_amendment_proposal_stage(),
    stage_order=["observe", "inspect", "evaluate", "amend"],  # Custom order
)

trace = improver.run_once("/path/to/skill", logs_dir="./runs")

# Extract proposals from amend stage
for step in trace.steps:
    if step.name == "amend":
        proposals = step.output.get("proposals", [])
        for p in proposals:
            print(f"{p['type']}: {p['description']}")

# Preview accepted file changes without mutating the skill yet
patch_stage = create_patch_apply_stage(mode="plan")
plan = patch_stage({
    "skill_path": "/path/to/skill",
    "amend": {"proposals": proposals},
})
print(plan["applied_count"])
```

See:
- `examples/golden_evaluator_example.py` for basic evaluation
- `examples/full_loop_with_proposals.py` for end-to-end workflow with proposals

## Architecture

```
Skill Auto-Improver MVP
├── src/skill_auto_improver/
│   ├── models.py                 # RunTrace, StepResult
│   ├── logger.py                 # TraceLogger (JSON serialization)
│   ├── loop.py                   # SkillAutoImprover pipeline + factories
│   ├── evaluator.py              # Golden fixtures + evaluation logic
│   ├── proposer.py               # Amendment proposal engine
│   ├── ab_evaluator.py           # A/B comparison + regression detection
│   ├── applier.py                # Proposal apply/plan flow + backup snapshots
│   ├── operating_memory.py       # Skill-level doctrine/lessons/todo/gotchas
│   ├── shared_brain.py           # Multi-skill shared memory blocks (NEW)
│   ├── orchestrator.py           # Multi-skill coordination layer (NEW)
│   └── cli.py                    # CLI for trial, scaffold, and orchestration
├── tests/
│   ├── test_loop.py              # 39 tests (pipeline, integration)
│   ├── test_evaluator.py         # 11 tests (fixtures, evaluation)
│   ├── test_proposer.py          # 10 tests (proposals, severity, confidence)
│   ├── test_ab_evaluator.py      # 9 tests (A/B comparison, regression detection)
│   ├── test_applier.py           # 6 tests (apply flow, backups, dry-run safety)
│   ├── test_operating_memory.py  # 10 tests (scaffold creation/preservation)
│   ├── test_shared_brain.py      # 22 tests (memory blocks, cross-skill learning) (NEW)
│   ├── test_orchestrator.py      # 15 tests (multi-skill coordination) (NEW)
│   ├── test_cli.py               # 7 tests (CLI commands)
│   └── test_examples.py          # 1 test (real skill demo)
├── examples/
│   ├── golden_evaluator_example.py        # Golden fixtures example
│   ├── full_loop_with_proposals.py        # Full observe→inspect→evaluate→amend
│   ├── ab_evaluation_example.py           # A/B regression detection (3 scenarios)
│   ├── real_skill_guarded_trial.py        # Real skill trial with rollback
│   └── real_skill_demo/                   # Minimal runnable skill example
├── docs/
│   ├── README.md                 # This file
│   ├── ROADMAP.md                # Progress + next steps
│   ├── MULTI_SKILL_GUIDE.md      # Multi-skill orchestration guide (NEW)
│   ├── BUILD_LOG_2026-03-16_AFTERNOON.md # Development history
│   └── ARCHITECTURE.md           # Detailed system design (future)
```

## Test Coverage

**Total: 126 unit tests, all passing.**

- Loop tests (39): successful run, failure short-circuit, noop smoke run, golden evaluation integration, custom stage order, guarded patch acceptance, guarded auto-rollback, trace evaluation metadata persistence, trace patch-trial metadata persistence, promotion awareness, fixture-level policy gates, change budget enforcement, etc.
- Evaluator tests (11): fixture loading (3), snapshot evaluation (3), batch evaluation (3), report serialization (1), pipeline integration (1)
- Proposer tests (10): instruction proposals (1), test case proposals (1), reasoning proposals (1), multiple failures (1), empty failures (1), no-delta handling (1), report serialization (1), confidence levels (1), severity escalation (2), full integration (1)
- A/B Evaluator tests (9): all-recovered scenario, no-regression improvement, regression detection, mixed outcomes, new fixtures, empty reports, pass rate calculations, serialization, property tests
- Patch applier tests (6): backup creation, fixture file creation, dry-run safety, duplicate skipping, unsupported proposal skipping, loop-stage planning
- Operating Memory tests (10): scaffold creation, preservation, fixture-aware profiles, promotion memory, etc.
- **Shared Brain tests (22)**: directive matching, promotion wisdom recording/merging, regression patterns, fixture library, skill mastery, persistence, cross-skill learning
- **Orchestrator tests (15)**: orchestration runs, skill context generation, brain state accumulation, persistence, multi-skill coordination
- CLI tests (7): trial command, scaffold command, memory operations
- Example tests (1): real skill guarded trial with rollback demo

Run tests:
```bash
cd skill-auto-improver
PYTHONPATH=./src python3 -m unittest discover tests/ -v
```

Run a concrete patch trial:
```bash
cd skill-auto-improver
PYTHONPATH=./src python3 -m skill_auto_improver.cli trial \
  --skill-path /path/to/target-skill \
  --fixtures /path/to/fixtures.json \
  --proposals /path/to/proposals.json
```

Run the same trial with stricter auto-apply policy:
```bash
cd skill-auto-improver
PYTHONPATH=./src python3 -m skill_auto_improver.cli trial \
  --skill-path /path/to/target-skill \
  --fixtures /path/to/fixtures.json \
  --proposals /path/to/proposals.json \
  --min-confidence 0.90 \
  --accepted-severities warning critical
```

Persist a structured trace JSON for a real trial run:
```bash
cd skill-auto-improver
PYTHONPATH=./src python3 -m skill_auto_improver.cli trial \
  --skill-path /path/to/target-skill \
  --fixtures /path/to/fixtures.json \
  --proposals /path/to/proposals.json \
  --logs-dir ./runs
```

Current CLI evaluator supports simple file-content assertions by fixture:
```json
[
  {
    "name": "formal_greeting_present",
    "input_data": {"path": "SKILL.md"},
    "expected_output": {
      "contains": ["Use the formal greeting."],
      "not_contains": ["Do not use the formal greeting."]
    }
  }
]
```

It also supports lightweight command probes for more realistic skill checks:
```json
[
  {
    "name": "check_formal_greeting_runtime",
    "input_data": {
      "command": ["python3", "check_skill.py"],
      "timeout_seconds": 10
    },
    "expected_output": {
      "exit_code": 0,
      "stdout_contains": ["formal greeting ok"],
      "stdout_not_contains": ["formal greeting missing"],
      "stderr_contains": [],
      "stderr_not_contains": ["Traceback"]
    }
  }
]
```

## Security & Audit

### Zero External Dependencies

**Verified in `setup.py`:**
- `install_requires=[]` — no external packages required
- All functionality uses only Python standard library (dataclasses, pathlib, json, subprocess, etc.)
- Safe to run in restricted environments with no network access

**Verification:**
```bash
# Confirm zero deps
$ python setup.py check
$ grep install_requires setup.py
# install_requires=[],
```

### Execution Isolation

Proposed patches are executed in **isolated Python subprocess** with:

- **30-second timeout** (hard limit, prevents hangs)
- **Limited environment** (no credentials leakage)
- **No shell execution** (no injection attacks)
- **Captured I/O** (stdout/stderr logged separately)
- **Automatic rollback on failure** (test-driven safety)

**How it works:**
```python
# Code runs here (isolated subprocess)
proc = subprocess.run(
    [sys.executable, "-c", test_code],
    timeout=30,              # ← Hard timeout
    capture_output=True,     # ← I/O captured
    text=True,
    env={"PYTHONPATH": workspace},  # ← Limited env
)
```

For detailed isolation architecture and audit procedures, see [CODE_AUDIT_GUIDE.md](./CODE_AUDIT_GUIDE.md).

### Logging & Audit Trail

Every operation is logged with timestamp, action, and result:

- **Observe logs:** What behavior was observed
- **Inspect logs:** Proposals generated (JSON for easy parsing)
- **Amend logs:** Patches applied, before/after diffs
- **Evaluate logs:** Pass/fail metrics, regressions detected
- **Execute logs:** Subprocess stdout/stderr

**Example audit trail:**
```
2026-03-24 10:15:23 [OBSERVE] Loaded skill from SKILL.md
2026-03-24 10:15:24 [INSPECT] Generated 2 proposals (confidence: 0.85, 0.80)
2026-03-24 10:15:25 [USER] Approved patches via CLI
2026-03-24 10:15:26 [AMEND] Backup: skill-2026-03-24_10-15-26.zip
2026-03-24 10:15:27 [EXECUTE] Test passed in 2.3s
2026-03-24 10:15:28 [EVALUATE] Pass rate improved: 0.67 → 0.89 ✓
```

All logs retained for 30 days (configurable), older logs archived.

### Change Approval & Review

**Required approval gate before applying changes:**

```
OBSERVE → INSPECT → [USER REVIEWS & APPROVES] → AMEND
```

User must explicitly approve patches before they're applied:

```bash
$ skill-auto-improver improve my-skill \
    --show-proposals      # Review proposals
    # User reads proposals, decides...
    --approve             # Explicit approval required
```

No patches are applied without user approval.

### Backup & Rollback

- **Automatic backup** created before any AMEND operation
- **Automatic rollback** if test fails after patch
- **Manual rollback** available on-demand

```bash
# Rollback to previous state
$ skill-auto-improver rollback --skill my-skill --backup 2026-03-24_10-15-27

# List available backups
$ skill-auto-improver list-backups --skill my-skill
```

Backups retained for 60 days (configurable), with integrity verification.

For operational procedures and disaster recovery, see [OPERATIONAL_SAFETY.md](./OPERATIONAL_SAFETY.md).

### Code Review Points

**For security audits, focus on:**

1. **Path validation** (`applier.py` ~200-250): All file operations use absolute paths, sandboxed to workspace
2. **Subprocess execution** (`applier.py` ~350-400): Timeout enforced, no shell, environment whitelist
3. **Approval gates** (`loop.py`): User approval required before AMEND
4. **Backup procedures** (`applier.py`): Created before write, restored on failure
5. **Logging** (all stages): Every action logged with timestamp and result

See [CODE_AUDIT_GUIDE.md](./CODE_AUDIT_GUIDE.md) for line-by-line security review entry points.

---

## Roadmap

### Done ✅
1. ✅ Skill-run logging + trace schema
2. ✅ Golden test cases + evaluator
3. ✅ Amendment proposal engine
   - Instruction proposals (rewrite SKILL.md guidance)
   - Test case proposals (add regression fixtures)
   - Reasoning proposals (diagnostic hints)
   - Severity escalation based on mismatch count
   - Confidence scoring per proposal type
4. ✅ **A/B evaluation runner**: Before/after comparison with regression detection
   - Status tracking: recovered, regressed, stable_pass, stable_fail
   - Metrics: pass_rate_delta, recovered_count, regressed_count, is_safe
   - Union behavior: detects new test additions

### Next 🎯
5. ✅ **Skill amendment applier**: Apply or preview accepted proposals with backup snapshots
6. ✅ **Rollback + version history**: Safe reverts with diffs
7. ✅ **Guarded end-to-end patch trial**: apply candidate change, re-evaluate, and auto-rollback on regression
8. **CLI/example for real skill trial runs**: demonstrate proposal apply → evaluate → rollback decision
9. ✅ **Richer operator audit metadata**: include backup identifiers/diff summaries alongside patch-trial metadata
10. **CLI/example for real skill trial runs**: demonstrate proposal apply → evaluate → rollback decision against a concrete skill folder

## Design Decisions

- **Pluggable stages**: Each stage is a callable `(context: dict) -> dict`. Easy to swap, test, compose.
- **Golden fixtures over execution**: Focus on outcomes (expected vs actual) rather than brittle execution traces.
- **Delta computation**: Automatic diff shows exactly what changed, enabling faster debugging.
- **Error short-circuit**: First failure stops the loop, logs everything for inspection.
- **Structured traces**: JSON serialization + metadata enable post-run analysis and automation.

## Safety

- ✅ No destructive ops without backups; file mutations route through snapshot-backed apply flow
- ✅ Error-safe: catches exceptions, logs context, continues
- ✅ Version safety: traces include run_id, created_at, finished_at for audit trails
- ✅ Rollback supported both manually (`restore_backup`) and automatically in guarded patch trials

## Contributing

To add a new stage or improve evaluation:

1. Define the stage's `(context: dict) -> dict` contract
2. Add unit tests to `tests/`
3. Update `ROADMAP.md` with progress
4. Run `python3 -m unittest discover tests/ -v` to verify

## License

Internal use only.
