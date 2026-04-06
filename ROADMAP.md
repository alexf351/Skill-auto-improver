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
- [x] Ranked proposals actually drive apply/trial execution, not just trace output

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

### 2026-03-24 (Autonomous Build Block): Proposer + SharedBrain Integration
- Integrated `ProposalEngine` with `SharedBrain` for cross-skill learning in proposals
- ProposalEngine now accepts optional `SharedBrain` instance (backward compatible)
- Added `_load_brain_context()` to extract:
  - Core directives applicable to the skill
  - Skill mastery learnings (most useful proposal types)
  - Regression patterns for prevention
  - Promotion wisdom from other skills
  - Fixture library suggestions
- Enhanced confidence scoring with promotion wisdom boost (up to +0.09 for proven patterns)
- Enriched memory hints with cross-skill lessons and promotion history
- Proposal generation now threads `skill_name` parameter for brain queries
- Added graceful degradation: proposals work even if brain queries fail
- Added 10 new unit tests covering:
  - Brain acceptance and backward compatibility
  - Context loading from brain
  - Confidence boosting from promotion wisdom
  - Memory hints with cross-skill lessons
  - Proposal ranking with brain directives
  - Full integration flow
- **Total: 147 unit tests, all passing** (+10 from integration tests)

### 2026-03-24 (Afternoon Build Block): Memory-Driven Proposal Ranking
- Implemented `MemoryDrivenRanker` in `src/skill_auto_improver/memory_ranking.py` for intelligent proposal reordering
- Added `FixtureSuccessRecord` to track per-fixture proposal outcomes (accepted/rejected)
- Added `FixtureSimilarity` for finding similar fixtures and borrowing success patterns
- Ranking considers:
  - Direct acceptance rate for proposal type on specific fixture
  - Recency bonus (recent successes weight more heavily)
  - Difficulty adjustment (hard fixtures prioritize reliable types)
  - Similarity borrowing (similar fixtures' success guides unknown fixtures)
- Added structured persistence to `data/fixture-success.jsonl` for cross-session memory
- Added 27 new unit tests covering all ranking scenarios and edge cases
- Added interactive demo: `examples/memory_driven_ranking_demo.py` with 5 scenarios
- **Total: 174 unit tests, all passing** (+27 from memory ranking)

## Next Highest-Leverage Increment
- Automated promotion rules - Apply learned acceptance rules without operator review
- Brain-backed recent-trial fusion in operator dashboard output
- Extend orchestration preflight from command-probe cwd containment into stronger unused-proposal review hints

### 2026-04-05 (Daily Autonomous Build Block): Command-Probe CWD Containment Guards
- Hardened command-based fixture evaluation so `input_data.cwd` cannot escape the target skill root
- Added shared containment behavior in the direct CLI/runtime evaluation path (`evaluate_command_skill`) so safety does not rely on orchestration-only preflight
- Extended orchestration fixture preflight to reject unsafe command-probe `cwd` values before unattended runs start
- Added focused CLI + orchestrator coverage for `../outside`-style cwd escapes
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_orchestrator -v`

### 2026-04-06 (Daily Autonomous Build Block): Inspect-Driven Hotspot Proposal Narrowing
- Connected inspect-stage hotspot signals to amendment proposal generation instead of leaving inspect as advisory-only
- `create_amendment_proposal_stage()` now passes inspect context into `ProposalEngine.generate_proposals()`
- Proposal generation now:
  - prioritizes hotspot fixtures ahead of other failures
  - shifts hotspot fixture ordering toward safer `test_case`/`artifact` work before broader instruction edits
  - annotates proposal scope metadata (`fixture_hotspot` vs `normal`) so downstream apply/review flows can see when a patch should stay fixture-local
  - makes hotspot instruction/artifact/test-case descriptions explicitly warn against broad rewrites
- Added focused proposer + loop coverage proving inspect hotspots reorder proposal output and mark narrower scope correctly
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_proposer tests.test_loop -v`

### 2026-04-06 (Afternoon Autonomous Build Block): Applied-Fixture-Scoped Change Budgets
- Fixed a rollback-safety bug in `change_guard`: fixture-level change-budget limits were being merged from every configured fixture policy, even when that fixture had no applied changes in the current trial
- `SkillPatchApplier` now persists `fixture_name` on applied changes, and `_build_change_guard()` only tightens limits from fixtures actually touched by the run
- This prevents unrelated strict fixture policies from causing false `change budget exceeded` rollbacks during otherwise safe guarded trials
- Added focused loop coverage proving untouched fixture policies no longer constrain accepted runs
- **Targeted checks run:** `PYTHONPATH=src python3 -m unittest tests.test_loop -v`

### 2026-04-04 (Afternoon Autonomous Build Block): Conflict-Clustered Proposal Preflight
- Tightened orchestration preflight review output so duplicate proposal collisions are clustered by shared target instead of emitted as a chain of pairwise duplicates
- `proposal_coverage_gap` messages now group:
  - repeated `(fixture_name, type)` collisions into a single `duplicate proposal target cluster ... indexes [...]` issue
  - repeated artifact `content.target_path` collisions into a single `conflicts across indexes [...]` issue
- This makes unattended batch debugging materially clearer when 3+ proposals pile onto the same target, without changing apply semantics or safety policy
- Added focused orchestrator + CLI coverage for clustered duplicate messages, including a 3-way artifact conflict case
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-04-03 (Afternoon Autonomous Build Block): Accepted-Type Policy Preflight
- Extended unattended orchestration policy checks to include proposal **type** eligibility, not just confidence/severity
- `SkillTrialConfig` now carries `accepted_types` (default: `instruction`, `test_case`) so orchestration config snapshots match actual auto-apply intent
- Preflight now flags fixtures whose proposals are present and otherwise valid, but all would still be skipped because their types fall outside the run's accepted-type gate
- This closes another cron/operator false-green case where an artifact-only proposal set could look ready yet never mutate anything during the real trial
- Surfaced these under the existing `proposal_policy_gap` channel with clearer policy text including `accepted_types=[...]`
- Added focused orchestrator + CLI coverage for type-only policy gaps plus config normalization/validation coverage for `accepted_types`
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-04-03 (Daily Autonomous Build Block): Proposal Policy-Gap Preflight
- Extended orchestration preflight beyond fixture/proposal presence into apply-policy realism for unattended runs
- Preflight now flags fixtures whose proposals all exist but would still be skipped by the trial's own policy gates:
  - `min_confidence`
  - `accepted_severities`
- This closes a subtle cron failure mode where a batch looks fully wired on paper yet cannot produce any amendment because every candidate is pre-disqualified by operator policy
- Surfaced these as auditable `proposal_policy_gap` issues in orchestrator output so operators can tell the difference between missing proposals vs policy-blocked proposals
- Added focused orchestrator + CLI coverage for policy-blocked fixtures
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-04-02 (Afternoon Autonomous Build Block): Artifact Target Conflict Preflight
- Extended orchestration preflight into proposal-conflict validation for unattended batches
- Preflight now rejects multiple artifact proposals that target the same in-skill `content.target_path`, because apply order becomes ambiguous and rollback/audit clarity degrades
- This complements existing `(fixture_name, type)` duplicate checks by covering cross-fixture write collisions on shared artifact files
- Added focused orchestrator + CLI coverage proving duplicate artifact target paths surface as `proposal_coverage_gap` issues before any write stage runs
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-04-02 (Daily Autonomous Build Block): Proposal Coverage Preflight
- Extended orchestration preflight into fixture/proposal coverage semantics for unattended runs
- Preflight now flags:
  - fixtures that have no matching proposal entry when both fixtures and proposals are supplied
  - duplicate proposal targets hitting the same `(fixture_name, type)` pair, which makes apply order ambiguous
- Surfaced these as auditable `proposal_coverage_gap` issues in orchestrator output instead of discovering them mid-trial
- Added focused orchestrator + CLI coverage proving missing fixture coverage and duplicate proposal targets are reported cleanly
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-04-01 (Afternoon Autonomous Build Block): Duplicate Fixture-Name Preflight
- Hardened orchestration fixture validation against duplicate `name` entries in a single fixtures file
- Preflight now rejects duplicate fixture names as `invalid_fixtures_shape` because they make proposal targeting and outcome attribution ambiguous in unattended runs
- Added focused orchestrator + CLI coverage proving duplicate fixture names surface clearly in batch output before any loop/apply stage runs
- **Targeted checks intended:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-03-31 (Afternoon Autonomous Build Block): Proposal↔Fixture Consistency Preflight
- Extended orchestration preflight into cross-file validation, not just per-file shape checks
- When both fixtures and proposals are supplied, preflight now rejects proposal entries whose `fixture_name` does not match any fixture declared in the fixtures file
- Added reusable proposal-payload normalization so list and `{proposals:[...]}` inputs share the same validation path
- This prevents unattended trial runs from applying or evaluating patches against non-existent fixture targets, which is safer and makes operator debugging faster
- Added focused orchestrator coverage proving mismatched proposal fixture references surface as `proposal_fixture_mismatch`
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator -v`

### 2026-04-01 (Daily Autonomous Build Block): Artifact Target-Path Safety Preflight
- Hardened orchestration preflight against unsafe artifact writes before any patch-trial stage runs
- Artifact proposals are now additionally validated for:
  - object `content`
  - non-empty string `content.target_path`
  - target path resolving inside the skill root (reject `../` escape attempts)
- This shifts artifact path traversal / accidental out-of-skill writes from apply-time skips into explicit preflight issues, which is safer for unattended cron batches and clearer for operators
- Added focused orchestrator + CLI coverage proving escaping artifact targets surface as `invalid_proposals_shape` in orchestration output
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-03-31 (Daily Autonomous Build Block): Semantic Orchestration Preflight Validation
- Extended orchestration preflight beyond mere file existence / list-shape checks into fixture + proposal semantics
- Fixtures are now validated for:
  - non-empty `name`
  - object `input_data`
  - exactly one probe mode: `input_data.path` xor `input_data.command`
  - string `path` values and non-empty string-list `command` values
  - object `expected_output`
- Proposals are now validated for:
  - non-empty `type`
  - non-empty `fixture_name`
  - numeric `confidence` bounded to `0.0-1.0` when present
  - non-empty string `severity` when present
- This shifts malformed orchestration batches from evaluate-time/runtime failures into auditable preflight issues, which is safer for unattended cron runs and more useful for operators
- Added focused orchestrator + CLI coverage proving malformed command/path fixtures and invalid proposal metadata surface as `preflight_issues` in batch output
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-03-30 (Afternoon Autonomous Build Block): Amendment Stage Evaluation Seeding
- Closed a real loop bootstrap gap in `create_amendment_proposal_stage()`:
  - when no prior `evaluate` step exists, the stage can now use its `golden_evaluator` parameter to score `actual_outputs` directly
  - generated proposals now work in smaller/default pipelines without requiring callers to manually pre-populate `context["evaluate"]`
- Added `evaluation_seed` to the amendment output when the stage self-computes failing fixture context, keeping the bootstrap path auditable in downstream logs/tests
- Added focused loop coverage proving:
  - seeded evaluation generates proposals from a failing golden fixture
  - the stage remains a no-op when neither `evaluate` results nor `actual_outputs` are available
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_loop -v`

### 2026-03-30 (Daily Autonomous Build Block): Orchestration Preflight Validation
- Added `TrialPreflightIssue` plus `MultiSkillOrchestrator.preflight_trial_config()` so orchestration batches now fail fast on bad local inputs before any improver stages run
- Preflight currently validates:
  - skill path exists and contains `SKILL.md`
  - optional fixtures file exists, parses as JSON list, and each entry has a `name`
  - optional proposals file exists, parses as JSON list / `{proposals:[...]}`, and each entry has a `type`
- `_run_skill_trial()` now emits an auditable `preflight` step + orchestration metadata instead of crashing or silently counting bad configs as successful trials
- `run.skill_outcomes[...]` now surfaces `status`, `preflight_ok`, and structured `preflight_issues` for operator/cron consumers
- Added focused orchestration + CLI coverage proving preflight failures are visible in JSON output and do not inflate success counters
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator tests.test_cli -v`

### 2026-03-29 (Afternoon Autonomous Build Block): Orchestration Config Validation Helpers
- Added `SkillTrialConfig.__post_init__()`, `validate()`, and `from_dict()` so orchestration batches now get a small schema layer instead of raw dataclass construction
- Config parsing now:
  - coerces path-like fields to `Path`
  - normalizes severity strings
  - rejects empty `skill_name`
  - rejects invalid `min_confidence` values outside `0.0-1.0`
  - rejects empty / malformed `accepted_severities`
- CLI loader now reports the failing config entry index for faster operator debugging on batch files
- Added focused coverage for normalized path coercion + invalid orchestration entry rejection
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_orchestrator -v`

### 2026-03-29 (Daily Autonomous Build Block): Orchestrator CLI Batch Runner
- Added `run-orchestration` CLI command so operators/cron jobs can execute multi-skill batches from a JSON config file instead of writing custom harness code
- Added `_load_orchestration_configs()` helper to parse `SkillTrialConfig` entries from disk with a simple list-based contract
- CLI now returns a structured orchestration summary including run metrics and per-skill outcomes
- Added CLI coverage for:
  - successful batch execution against a real skill folder
  - invalid non-list config rejection
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_orchestrator -v`

### 2026-03-28 (Afternoon Autonomous Build Block): Orchestrator Trace Normalization + Persistence
- Fixed a real orchestration audit gap: enriched per-skill traces are now rewritten after orchestration metadata + synthetic `patch_trial` context are attached, so persisted JSON matches in-memory state
- Added `MultiSkillOrchestrator._normalized_patch_trial_metadata()` so the orchestrator can consume both:
  - flat loop-level `metadata["patch_trial"]` written by `_update_trace_metadata()`
  - nested stage-output `patch_trial` payloads with `apply`/`ab` sub-objects
- This closes a metrics bug where accepted recoveries from flat trace metadata were previously invisible to shared-brain promotion accounting
- Added focused orchestrator coverage for:
  - flat patch-trial metadata insight extraction
  - persisted trace rewrite including orchestration metadata + synthetic `patch_trial` step
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_orchestrator -v`

### 2026-03-28 (Daily Autonomous Build Block): Golden Evaluation CLI + Trace Logging
- Added `evaluate-golden` CLI command for direct golden-fixture execution against real skill folders
- Reused existing file-content and command-probe fixture execution, so one command now covers both static and lightweight runtime golden checks
- Wired golden evaluation into the shared trace writer with normalized `metadata["evaluation"]` output (`mode: golden`)
- Set command exit status to fail when any fixture fails, making golden checks usable in cron/CI without parsing JSON first
- Added CLI coverage proving failing golden runs still persist trace artifacts with audit metadata intact
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_loop -v`

### 2026-03-27 (Afternoon Autonomous Build Block): Evaluation CLI Trace Coverage
- Closed an evaluation-loop logging gap outside guarded patch trials:
  - `evaluate-checklist` can now persist structured run traces via `--logs-dir`
  - `evaluate-hybrid` can now persist structured run traces via `--logs-dir`
- Added reusable `_write_trace()` helper so non-trial CLI commands share the same trace-writing path instead of bespoke logging code
- Expanded trace metadata summarization in `loop.py` so `metadata["evaluation"]` now captures:
  - golden evaluator summaries
  - checklist evaluator summaries
  - hybrid evaluator gate outcomes (`fixture_only`, `checklist_only`, `hybrid_either_or`, `hybrid_both_required`)
- Added CLI coverage proving persisted traces include command metadata plus normalized evaluation summaries for checklist + hybrid flows
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_loop -v`

### 2026-03-27 (Daily Autonomous Build Block): Config-Aware Orchestrated Trial Context
- Tightened the multi-skill orchestrator so each trial now builds and persists auditable orchestration context:
  - per-skill config snapshot (`min_confidence`, severities, fixture/proposal paths)
  - pre-trial shared-brain context
  - fixture-template suggestions keyed by requested fixture names when fixture files are present
- Added backward-compatible improver factory wiring:
  - old factories can still accept just `skill_path`
  - newer factories can optionally receive `(skill_path, config, brain_context)`
- Fixed orchestration outcome summaries to use per-trial counts instead of leaking cumulative run totals
- Promotion/regression recording now derives proposal types from actual applied/skipped changes rather than hard-coded defaults
- Added focused orchestrator tests covering metadata persistence, richer factory injection, and per-trial outcome accounting
- **Targeted checks:** `tests.test_orchestrator`

### 2026-03-26 (Afternoon Autonomous Build Block): Shared-Brain Operator Dashboard CLI
- Added `SharedBrain.summarize_dashboard(skill_name=None, limit=5)` to expose a compact operator-facing snapshot of:
  - block counts
  - top promotion wisdom entries
  - top regression patterns
  - most active skill mastery records
- Added CLI command:
  - `python3 -m skill_auto_improver.cli brain-dashboard --brain-dir ./shared_brain [--skill-name weather] [--limit 5]`
- Skill-focused dashboard mode now includes:
  - existing per-skill summary
  - fixture-template suggestions for the requested skill name
- Added unit coverage for both shared-brain ranking logic and CLI JSON output
- **Targeted checks:** `PYTHONPATH=src python3 -m unittest tests.test_shared_brain tests.test_cli -v`

### 2026-03-26 (Daily Autonomous Build Block): Fixture Suggestion CLI
- Added `SharedBrain.suggest_fixture_templates()` to turn fixture-library history into ranked, review-friendly suggestions
- Added `FixtureSuggestion` payload with similarity score, shared traits, expected behavior, anti-patterns, and reusable fixture template
- Added CLI command:
  - `python3 -m skill_auto_improver.cli suggest-fixtures --brain-dir ./shared_brain --fixture-name greeting_formal_check --limit 3`
- Added unit coverage for both shared-brain ranking and CLI JSON output
- **Targeted checks:** `tests.test_shared_brain` and `tests.test_cli`

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
1. ✅ Proposer integration - Thread brain context into proposal generation (2026-03-24, shipped)
2. ✅ Memory-driven proposal ranking - Use promotion wisdom to reorder proposals (2026-03-25, shipped)
3. Fixture suggestion - Recommend library fixtures for new skills
4. Unified operator dashboard - CLI for brain exploration
5. Automated promotion rules - Apply learned rules without manual intervention

### 2026-03-25 (Build Block): Loop Integration for Memory-Driven Ranking
- Implemented `create_proposal_ranking_stage()` to reorder proposals using `MemoryDrivenRanker`
- Added ranking stage to default pipeline: observe → inspect → amend → **rank** → evaluate
- Ranking stage handles dicts/proposals conversion and gracefully degrades on errors
- Made `rank` stage optional in `SkillAutoImprover` dataclass for backward compatibility
- Added 9 new integration tests covering:
  - Ranking by fixture success history
  - Empty/missing rank file handling
  - Metadata preservation during reordering
  - Pipeline integration with default ordering
  - Backward compatibility without rank stage
  - Grouping and ranking across multiple fixtures
  - Integration with proposal generator
- **Total: 207 unit tests, all passing** (+9 from ranking integration)

### 2026-03-25 (Afternoon Build Block): Ranked Proposal Handoff into Safe Apply/Trial
- Fixed a real loop gap: `rank` output now becomes the proposal source for downstream apply/trial stages instead of being ignored after reordering
- Added `_proposal_source()` in `loop.py` so guarded trials and patch-apply stages prefer ranked proposals when available, while staying backward compatible with amend-only contexts
- Added regression coverage proving a high-confidence ranked proposal can win over a low-confidence raw amend proposal during guarded trial execution
- Verified targeted suites: `tests.test_loop` and `tests.test_ranking_integration`
