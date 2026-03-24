# Skill Auto-Improver Roadmap

## Goal
Build an MVP that improves user-built skills via observe → inspect → evaluate → amend with rollback safety.
Expand to multi-skill orchestration with shared learning across skills.

## Milestones
1. ✅ **Skill-run logging + trace schema** (2026-03-14, shipped)
2. ✅ **Golden test cases + evaluator** (2026-03-15, shipped)
3. ✅ **Amendment proposal engine** (2026-03-16, shipped)
4. ✅ **A/B evaluation runner + regression checks** (2026-03-16, shipped)
5. ✅ **Rollback + version history** (2026-03-17, shipped)
6. ✅ **Persistent operating-memory layer** (doctrine, lessons, todo, gotchas, verification) (2026-03-20/21, shipped)
7. ✅ **Multi-skill shared brain + orchestration** (2026-03-24, shipped)

## Current Checklist
- [x] Observe/inspect/amend/evaluate loop
- [x] Skill-run logging + trace schema
- [x] Golden-output evaluator
- [x] Patch proposal generation
- [x] Patch proposal apply/plan flow with backup snapshots
- [x] Rollback restore command + version history browser
- [x] End-to-end before/after evaluation loop wiring

## Progress Log

### 2026-03-14: Baseline Loop + Trace Logging
- Implemented `SkillAutoImprover` with four pluggable stages: observe → inspect → amend → evaluate
- Added `RunTrace` schema with structured step results and metadata
- Added `TraceLogger` for JSON serialization to disk
- 4 unit tests covering happy path, failure handling, noop smoke run

### 2026-03-15: Golden-Output Evaluator
- Implemented `GoldenEvaluator` with fixture loading, snapshot/batch evaluation, delta computation
- Added `GoldenFixture` and `GoldenFixtureLoader` (JSON/dict support)
- Added `EvaluationReport` with pass_rate and per-fixture results
- Integrated `create_golden_evaluator_stage()` factory for drop-in use
- 11 unit tests covering all evaluator features
- **Total: 15 unit tests, all passing**

### 2026-03-16: Amendment Proposal Engine
- Implemented `ProposalEngine` to generate patches from failing test cases
- Three proposal types:
  - **Instruction proposals**: Rewrite SKILL.md guidance based on mismatches
  - **Test case proposals**: Add regression fixtures to prevent repeats
  - **Reasoning proposals**: Diagnostic hints with root cause hypotheses
- Added severity escalation: "warning" (1 mismatch) → "critical" (2+)
- Added confidence scoring: 0.8–0.9 per proposal type
- Added `create_amendment_proposal_stage()` factory for integration
- **NEW:** `stage_order` parameter in `SkillAutoImprover` for custom pipeline orderings (e.g., evaluate → amend)
- 10 unit tests covering all proposal types, integration, edge cases
- Full end-to-end example: `examples/full_loop_with_proposals.py` demonstrating observe → inspect → evaluate → amend
- **Total: 25 unit tests, all passing**

### 2026-03-16 (Afternoon): A/B Evaluation Runner
- Implemented `ABEvaluator` for comparing before/after evaluation reports
- Added `ABComparison` and `ABReport` with detailed metrics:
  - **Status tracking**: recovered (fail→pass), regressed (pass→fail), stable_pass, stable_fail
  - **Metrics**: pass_rate_delta, recovered_count, regressed_count, is_safe flag
  - **Union behavior**: tracks all fixtures across before/after (enables new test detection)
- Added `create_ab_evaluation_stage()` factory for loop integration
- Comprehensive regression detection with detailed per-fixture breakdown
- 9 new unit tests (all passing) covering:
  - All-recovered scenario
  - No-regression improvement
  - Regression detection
  - Mixed recovery + regression outcomes
  - New fixtures in after report
  - Empty reports
  - Pass rate calculations
  - Serialization to dict
- Full example: `examples/ab_evaluation_example.py` with 3 scenarios (baseline, regressions, mixed)
- **Total: 34 unit tests, all passing**

### 2026-03-17 (Afternoon): Patch Apply/Plan Flow + Backup Snapshots
- Implemented `SkillPatchApplier` in `src/skill_auto_improver/applier.py`
- Supports two meaningful proposal types out of the box:
  - **Instruction proposals**: append a reviewable SKILL.md amendment note
  - **Test case proposals**: append regression fixtures to `golden-fixtures.json`
- Added safe planning mode (`mode="plan"`) so proposals can be previewed without writing files
- Added backup snapshots under `.skill-auto-improver/backups/` before mutating existing files
- Added duplicate regression-fixture detection and default skip behavior for unsupported proposal types
- Added `create_patch_apply_stage()` factory for loop integration
- 6 new unit/integration tests covering backups, dry-run behavior, duplicate skipping, and loop-stage planning
- **Total: 40 unit tests, all passing**

### 2026-03-18: Rollback Restore + Backup History Browser
- Implemented `list_backups()` in `SkillPatchApplier` to expose snapshot inventory ordered newest-first
- Implemented `restore_backup()` with structured `RestoreReport` so bad amendment applies can be reverted safely
- Added `BackupEntry` + `RestoreReport` dataclasses for version-history/restore responses
- Added 3 new unit tests covering backup listing, successful restore, and missing-backup failure handling
- **Total: 43 unit tests, all passing**

### 2026-03-18: Guarded End-to-End Patch Trial
- Implemented `create_safe_patch_trial_stage()` in `loop.py` to wire baseline eval → apply proposals → after eval → A/B comparison in one guarded flow
- Added automatic rollback of applied files when the after-state introduces regressions
- Added shared evaluation-report reconstruction helper so A/B stages and guarded trials use the same schema path
- Added 2 end-to-end loop tests covering safe acceptance and auto-rollback on regression
- Fixed `tests/test_ab_evaluator.py` import path so the full suite runs cleanly via `python3 -m unittest discover tests -v`
- **Total: 45 unit tests, all passing**

### 2026-03-18 (Afternoon): Trace Metadata for Evaluation + Patch Trials
- Added `_update_trace_metadata()` in `loop.py` so run traces capture compact evaluation summaries without requiring step-payload inspection
- Persisted guarded patch-trial audit fields into `RunTrace.metadata["patch_trial"]` (accepted/rolled_back counts, applied/skipped counts, pass-rate delta, regressions)
- Added 2 loop tests covering persisted evaluation metadata and persisted patch-trial metadata in both in-memory traces and written JSON logs
- **Total: 47 unit tests, all passing**

### 2026-03-19: Backup IDs + Compact Diff Summaries
- Enriched `AppliedChange` with `backup_id` and `diff_summary` payloads so each proposed/applicable change is easier to review and trace
- Added diff previews for both instruction-note patches and regression-fixture appends, including dry-run plan mode
- Lifted backup IDs + compact diff summaries into `RunTrace.metadata["patch_trial"]` for faster operator audit of safe/rolled-back trials
- Expanded unit tests to assert diff previews and backup identifiers in both apply reports and persisted trace metadata
- **Total: 47 unit tests, all passing**

## Next Highest-Leverage Increment
- Tighten proposal acceptance policy (e.g. confidence/severity thresholds before auto-apply)
- Add an operator-facing backup/diff browser helper on top of the new audit metadata
- Expand the CLI beyond file-content probes into pluggable real skill evaluators
 a simple file-content probe evaluator so concrete `SKILL.md` checks can run without custom harness code
- Added 2 CLI tests covering both safe acceptance and regression-triggered rollback paths
- **Total: 49 unit tests, all passing**

### 2026-03-20: Persistent Operating-Memory Scaffold
- Added `operating_memory.py` to scaffold a reusable per-skill execution doctrine layer
- Scaffold creates:
  - `doctrine.md`
  - `lessons.md`
  - `todo.md`
  - `gotchas.md`
  - `verification.md`
  - `data/preferences.json`
  - `data/run-history.jsonl`
  - `data/feedback.log`
- Added CLI command: `scaffold-memory --skill-path <path> [--force]`
- Added tests for creation, preservation, and forced overwrite behavior
- Direction shift locked in: auto-improver is evolving from prompt improver → full skill-system improver

### 2026-03-20: Proposal Acceptance Gates
- Added confidence/severity gating to `SkillPatchApplier.apply()` so auto-apply can be constrained by explicit operator policy
- Threaded `min_confidence` + `accepted_severities` through `create_patch_apply_stage()` and `create_safe_patch_trial_stage()`
- Extended CLI `trial` command with `--min-confidence` and `--accepted-severities`
- Added applier + CLI coverage for blocked low-confidence and disallowed-severity proposals
- **Total: 52 unit tests, all passing**

### 2026-03-21: Operating-Memory Trial Logging
- Added `OperatingMemory` helper in `src/skill_auto_improver/operating_memory.py`
- Safe patch trials now auto-bootstrap the memory scaffold and write a structured JSONL run record to `data/run-history.jsonl`
- Trial outcomes now update operator-facing memory files automatically:
  - `todo.md` review note
  - `verification.md` proof block
  - `lessons.md` on accepted recoveries
  - `gotchas.md` on regressions / rollback events
- Threaded the memory result back through `create_safe_patch_trial_stage()` so CLI/operators can inspect what was updated
- Added operating-memory unit coverage plus loop assertions proving history + gotcha updates
- **Total: 54 unit tests, passing**

### 2026-03-21 (Later): Fixture-Aware Memory Profiles
- Upgraded operating-memory ingestion from flat bullet extraction to structured lesson/gotcha parsing
- `load_context()` now emits per-fixture profiles under `proposal_hints.fixture_profiles`
- Added support for `proposal.fixture_policies` in `data/preferences.json` so a skill can express fixture-specific:
  - boost / avoid terms
  - preferred proposal types
  - confidence floors
  - accepted severity hints
- Proposal generation now consumes those fixture profiles to produce sharper memory hints, stronger confidence/severity biasing, and risk-aware ordering
- Added unit coverage for structured memory parsing, fixture-specific policy loading, and regression-priority proposal ordering
- **Total: 63 unit tests, passing**

### 2026-03-21 (Build Block): Fixture-Level Policy Gates in Guarded Apply/Trial
- Wired `proposal.fixture_policies` from operating memory into guarded apply decisions, not just proposal generation
- `SkillPatchApplier.apply()` now supports fixture-specific policy overrides for:
  - `min_confidence`
  - `accepted_severities`
- Safe patch trials now pass merged memory fixture policy into apply flow, so risky fixtures can demand stricter acceptance rules before any write lands
- Added applier, loop, and CLI coverage proving fixture-level policy can block a proposal even when global CLI thresholds are permissive
- **Total: 67 unit tests, passing**

### 2026-03-21 (Afternoon Build Block): CLI Trial Trace Logging
- Added optional `--logs-dir` support to `trial` so real guarded runs persist a structured `RunTrace` JSON artifact instead of only printing stdout
- Trial traces now capture:
  - `before_eval`
  - guarded `apply_trial` result (with patch-trial metadata)
  - `after_eval`
  - CLI invocation metadata (`fixtures_path`, `proposals_path`)
- Added CLI coverage proving trace persistence and metadata integrity for accepted guarded trials
- **Total: 68 unit tests, expected passing**

### 2026-03-23 (Afternoon Build Block): Real Skill Demo for Trace-Aware Guarded Trials
- Added `examples/real_skill_demo/` with a minimal runnable skill folder, command-probe checker, golden fixtures, and both safe/regression proposal sets
- Added `examples/real_skill_guarded_trial.py` to demonstrate an operator-facing end-to-end flow:
  - safe recovery acceptance
  - trace-aware observe/inspect pass over recent runs
  - promoted-baseline regression rollback on the next candidate patch
- Added `tests/test_examples.py` to verify the demo actually runs and proves both acceptance + rollback behavior
- **Total: 77 unit tests, expected passing**

## Next Highest-Leverage Increment
- Expand evaluator hooks beyond lightweight command probes into reusable real skill execution harnesses while preserving guarded acceptance rules
- Add a thin CLI wrapper for observe/inspect summaries so operators can inspect recent run signals without writing custom scripts

### 2026-03-23: Trace-Aware Observe/Inspect Stages
- Added `load_traces()` + `summarize_traces()` in `logger.py` so recent run logs can be consumed as structured operating signals instead of only archived JSON
- Added `create_recent_run_observer_stage()` to summarize recent trial history for the target skill:
  - acceptance-reason counts
  - regression/recovery totals
  - latest failure/success snapshots
  - compact human-usable signals for the next loop pass
- Added `create_trace_inspect_stage()` to convert those signals into priorities/hypotheses (e.g. promoted-baseline protection, proposal-gate mismatch, smallest-safe-change bias)
- Added loop coverage proving trace summaries are skill-filtered and the inspect stage prioritizes blocked-proposal / regression work correctly
- **Total: 76 unit tests, expected passing**

### 2026-03-23 (Late Night): Smarter Updates + Memory-Driven Change Budgets
- `SkillPatchApplier` now updates matching fixture-specific markdown sections in place instead of endlessly appending duplicate instruction/artifact blocks
- Added heading-aware refresh behavior for dedicated artifact files (for example `references/auto-improver/<fixture>.md`)
- Extended operating-memory policy with change-budget controls:
  - `max_changed_targets`
  - `max_added_lines`
  - fixture-level overrides for both
- Safe patch trials now compute a `change_guard` from actual applied diff summaries and can reject + rollback candidates with acceptance reason `change budget exceeded`
- Rollback logic now deletes newly created files when a rejected trial has no backup snapshot to restore
- Added applier + loop coverage for in-place section refreshes and memory-driven rollback on excessive churn
- **Total: 89 unit tests, passing**

### 2026-03-23 (Night): Promotion-Aware Ranking + Full-Artifact Support
- Promotion memory now flows all the way into proposal ordering via `proposal_hints.promotion_profiles`
- Historically protected fixtures now bias toward safer companion work:
  - `test_case` proposals rank ahead of broad instruction edits
  - `artifact` proposals can target supporting skill files outside `SKILL.md`
- Added `artifact` apply support for relative files under the skill root (e.g. `references/auto-improver/<fixture>.md`)
- Added fixture-policy gate `required_proposal_types`, enabling protected fixtures to block instruction-only auto-apply until a regression test accompanies the change
- Guarded trials can auto-derive that gate from promotion history when `require_test_case_for_protected_fixtures` is enabled
- Added proposer/applier/loop coverage for ranking, artifact writes, and protected-fixture apply blocking
- **Total: 83 unit tests, expected passing**

### 2026-03-23 (Late Night): Structure-Aware Artifact Selection
- Proposal generation now inspects target skill structure before deciding where companion artifacts should live
- Added `skill_profile` extraction in `ProposalEngine.generate_proposals(..., skill_path=...)`
- Artifact targeting now adapts to the skill's existing layout:
  - `references/auto-improver/*` for reference-heavy skills
  - `docs/auto-improver/*` for docs-heavy skills
  - `checklists/auto-improver/*` for checklist-driven skills
- Artifact payloads now carry `structure_reason`, `skill_profile`, and structure-specific format hints (`markdown_append` vs `markdown_checklist`)
- Amendment-stage integration now threads `skill_path` through proposal generation so structure-aware targeting works in real loop runs, not just direct engine calls
- Added proposer/applier/loop coverage for docs-targeted artifacts, checklist-style artifact bodies, and structure context propagation
- **Total: 86 unit tests, passing**

### 2026-03-22: Fixture-Targeted Latest-Restore Helper
- Added `restore_latest_backup(target_name=...)` to `SkillPatchApplier` so operators can revert the newest snapshot for a specific file without looking up backup ids first
- Added CLI command: `restore-latest-backup --skill-path <path> --target-name SKILL.md`
- Failure path now returns a structured `RestoreReport` when a target has no backups instead of forcing manual inspection first
- Added applier + CLI coverage for both successful latest-restore and no-backup failure cases
- **Total: 72 unit tests, expected passing**

### 2026-03-22 (Afternoon Build Block): Command-Probe Evaluator Hooks
- Expanded CLI trial evaluation beyond file-content probes into lightweight command execution fixtures
- Added `evaluate_command_skill()` + `evaluate_skill_fixtures()` so a guarded run can mix:
  - `input_data.path` file assertions
  - `input_data.command` runtime probes executed inside the target skill folder
- Command fixtures now support expectations for:
  - `exit_code`
  - `stdout_contains` / `stdout_not_contains`
  - `stderr_contains` / `stderr_not_contains`
- Added CLI coverage proving both direct command-probe evaluation and end-to-end guarded trial recovery against a command-based fixture
- **Total: 74 unit tests, expected passing**

### 2026-03-20 (Afternoon): Operator-Facing Backup Inspection Helper
- Added `inspect_backups()` to `SkillPatchApplier` for review-friendly snapshot inspection
- New `BackupInspection` payload includes:
  - backup metadata (`backup_path`, `created_at`, `target_path`)
  - whether the current target still exists
  - compact diff preview between the backup snapshot and the current live file
- Added CLI command: `inspect-backups --skill-path <path> [--limit N]`
- Operator can now quickly answer: *what changed since this snapshot, and is this the one I want to restore?*
- Added unit coverage for both applier-level backup inspection and CLI JSON output
- **Total: 54 unit tests, expected passing**

### 2026-03-24 (Subagent Session): Multi-Skill Shared Brain + Orchestration Layer

**Files:**
- `src/skill_auto_improver/shared_brain.py` (450 lines)
- `src/skill_auto_improver/orchestrator.py` (280 lines)
- `tests/test_shared_brain.py` (400 lines, 22 tests)
- `tests/test_orchestrator.py` (300 lines, 15 tests)
- `examples/multi_skill_orchestration_demo.py` (350 lines)
- `docs/MULTI_SKILL_GUIDE.md` (600 lines)
- `docs/COMPLETION_REPORT.md` (400 lines)

**Implemented:**

1. **Shared Brain** - Structured, persistent memory for multi-skill learning
   - `CoreDirective`: System-wide operational rules with pattern matching for skills
   - `PromotionWisdom`: Why patches succeeded, across which skills, with lessons
   - `RegressionPattern`: Common failure modes observed in multiple skills
   - `FixtureLibrary`: Reusable fixture patterns with successful skill history
   - `SkillMastery`: Per-skill learned insights (proposal types, trial history, common issues)
   - All five blocks persist to JSON and auto-load on init
   - Default directives pre-populated on first run

2. **Multi-Skill Orchestrator** - Coordinates improvement runs across multiple skills
   - `SkillTrialConfig`: Configuration for a single skill trial
   - `MultiSkillOrchestrator`: Runs improvement trials on multiple skills sequentially
   - `OrchestrationRun`: Captures results, metrics, and cross-skill insights
   - Pre-trial context generation from shared brain
   - Orchestration logs with full traceability

3. **Cross-Skill Learning Patterns**
   - Promotion wisdom cascading: Success in one skill informs proposals in others
   - Regression prevention: Patterns learned from one skill prevent regressions in others
   - Fixture library reuse: Proven patterns from successful skills bootstrap new skills
   - Skill mastery tracking: Understand what works best for each skill type
   - Directive application: System-wide rules applied to multiple skills

4. **Comprehensive Testing**
   - 22 unit tests for shared brain (directives, promotion wisdom, regression patterns, library, mastery)
   - 15 unit tests for orchestrator (initialization, runs, context, persistence)
   - All tests passing, no breaking changes to existing 89 tests
   - **Total: 126 unit tests, all passing**

5. **Documentation**
   - MULTI_SKILL_GUIDE.md: Complete API reference with examples and best practices (600 lines)
   - COMPLETION_REPORT.md: Implementation details and metrics (400 lines)
   - Interactive demo: multi_skill_orchestration_demo.py with 5 concrete scenarios
   - Updated README.md with multi-skill section and test coverage
   - Updated ROADMAP.md with completion milestone
   - Full docstrings and type hints throughout

**Key Features:**
- ✅ Persistent memory: All blocks survive sessions via JSON
- ✅ Auto-merging: Wisdom entries merge across skills (no duplication)
- ✅ Fast queries: Lookups by fixture name, skill name, pattern name
- ✅ Pre-trial context: Skills load brain state before improvement
- ✅ Type hints: Full Python 3.9+ type annotations
- ✅ No dependencies: Uses stdlib only (json, uuid, pathlib, dataclasses)
- ✅ Clean code: PEP 8, docstrings, error handling

**Next Steps:**
1. Proposer integration - Thread brain context into proposal generation
2. Memory-driven proposal ranking - Use promotion wisdom to reorder proposals
3. Fixture suggestion - Recommend library fixtures for new skills
4. Unified operator dashboard - CLI for brain exploration
5. Automated promotion rules - Apply learned rules without manual intervention

- **Total: 126 unit tests, all passing**
