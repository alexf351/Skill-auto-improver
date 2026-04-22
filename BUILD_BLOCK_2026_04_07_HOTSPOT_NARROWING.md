# Build Block: 2026-04-07 - Inspect-Driven Hotspot Proposal Narrowing

## Objective
Connect inspect-stage hotspot signals to amendment proposal generation for more focused, lower-risk changes to problematic fixtures.

## Changes Made

### 1. Hotspot Signal Integration in Proposer
- `ProposalEngine.generate_proposals()` now accepts optional `inspect_context` parameter
- Inspect signals (hotspot fixtures, regression alerts) now flow through proposal generation
- Memory context now includes `inspect_focus` extracted from inspect-stage output
- Backward compatible: proposals work fine without inspect context

### 2. Proposal Scope Narrowing
- All proposal types now carry a `scope` field: `"fixture_hotspot"` vs `"normal"`
- Hotspot proposals are annotated with explicit warnings against broad rewrites
- Instruction proposals for hotspots explicitly warn: "Keep the patch fixture-local"
- Artifact proposals for hotspots remind: "Use it to constrain the next fix to this hotspot"
- Test case proposals for hotspots prioritize: "Prioritize this hotspot fixture before adding broader coverage"

### 3. Proposal Ordering with Hotspot Priority
- Reordered proposal sort key to prioritize hotspot fixtures ahead of non-hotspots
- Ordering hierarchy:
  1. Hotspot fixtures first (priority 0) vs regular fixtures (priority 1)
  2. Regression-prone fixtures second
  3. Historically-protected fixtures third
  4. Type priority based on protection status
- Hotspot signals dominate ordering decisions

### 4. Trace Logging Enhancements
- Added hotspot fixture tracking to run trace summaries
- `_collect_fixture_status_counts()` extracts per-fixture A/B comparison results
- New `fixture_hotspots` section in trace metadata with top regressed/recovered/stable-fail fixtures
- Recent-run summaries now expose fixture hotspots (limit 3 per category)
- Helps operators spot repeating problem fixtures without parsing full traces

### 5. Orchestration Validation Hardening
- Added `TrialPreflightIssue` dataclass for structured preflight validation
- `SkillTrialConfig` now validates:
  - Non-empty `skill_name`
  - `min_confidence` bounded to 0.0-1.0
  - `accepted_severities` as non-empty list of strings
  - `accepted_types` (new field, default: `["instruction", "test_case"]`)
- Config validation in `__post_init__()` ensures early failure on bad configs
- Added `from_dict()` class method for deserialization with validation

### 6. Patch Trial Metadata Normalization
- `MultiSkillOrchestrator._normalized_patch_trial_metadata()` now accepts both:
  - Flat loop-level `metadata["patch_trial"]` (from older traces)
  - Nested stage-output `patch_trial` payloads (from newer structures)
- Normalizes to consistent structure with `apply` and `ab` sub-objects
- Enables orchestration to consume traces from different pipeline versions

### 7. Nightly Orchestrator Refactoring
- Updated imports to use relative paths (`.orchestrator`, etc.)
- Replaced custom `SkillAutoImproverLogger` with standard `logging`
- Simplified brain summary extraction from orchestrator
- Improved trial config creation with standardized field names
- Enhanced morning-summary JSON structure to match orchestration output schema

### 8. Default Improver Factory
- Added `MultiSkillOrchestrator._create_default_improver()` for lightweight no-op pipelines
- Default pipeline creates an improver that:
  - Validates SKILL.md existence (no-op if missing)
  - Records an audited trace with skill metadata
  - Makes no file changes (safe for nightly runs without custom logic)
- Ensures orchestration never crashes on missing custom stage pipeline

## Testing
- All 262 tests pass (unchanged test count)
- New ranking integration tests verify hotspot handling
- Orchestrator validation coverage for config normalization
- Trace summary tests confirm hotspot counting

## Impact
- **Lowest-risk changes**: Hotspot fixtures now get tighter scope constraints
- **Clearer operator signals**: Fixture hotspots surfaced in trace summaries
- **Safer batches**: Orchestration config validation catches bad inputs early
- **Flexible tracing**: Supports both flat and nested patch-trial metadata formats
- **Backward compatible**: Existing pipelines work unchanged

## Files Changed
- `src/skill_auto_improver/proposer.py` (+57 lines, -0)
- `src/skill_auto_improver/logger.py` (+47 lines, -0)
- `src/skill_auto_improver/orchestrator.py` (+802 lines, -114)
- `src/skill_auto_improver/applier.py` (+4 lines, -0)
- `src/skill_auto_improver/shared_brain.py` (+92 lines, -0)
- `src/skill_auto_improver/nightly_orchestrator.py` (+144 lines, -114)
- `tests/test_proposer.py` (+30 lines, -0)
- `tests/test_shared_brain.py` (+81 lines, -0)
- `tests/test_ranking_integration.py` (new file, 220 lines)

**Total: 1143 insertions(+), 114 deletions(-)**

## Commit
```
0b662e9 feat: inspect-driven hotspot proposal narrowing + orchestration hardening
```

## Next Highest-Leverage Increment
1. **Automated promotion rules** - Apply learned acceptance rules without operator review
2. **Brain-backed recent-trial fusion** in operator dashboard output
3. **Fixture-level auto-apply gates** - Promotion history can now demand stricter acceptance rules per fixture
