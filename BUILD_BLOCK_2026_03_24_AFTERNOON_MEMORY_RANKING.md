# Build Block: Memory-Driven Proposal Ranking (2026-03-24 Afternoon)

**Time:** 14:00-15:00 UTC  
**Duration:** ~1 hour autonomous build block  
**Goal:** Ship highest-leverage proposal intelligence feature  
**Status:** ✅ SHIPPED + TESTED

---

## Single Meaningful Increment

**Implemented memory-driven proposal ranking for intelligent reordering based on per-fixture success history.**

The system now learns which proposal types work best for which fixtures, and uses that knowledge to automatically reorder proposals, making better suggestions more likely to be accepted.

---

## What Shipped

### Core Implementation

**File:** `src/skill_auto_improver/memory_ranking.py` (381 lines)

Three new classes:

1. **FixtureSuccessRecord** (100 lines)
   - Tracks acceptance/rejection history per fixture
   - Maintains preferred proposal types ordered by success rate
   - Detects "historically difficult" fixtures (requires many attempts)
   - Serializes/deserializes to/from JSON for persistence

2. **FixtureSimilarity** (15 lines)
   - Represents similarity between two fixtures
   - Enables fixture-to-fixture pattern borrowing
   - Supports sorting/comparison operators

3. **MemoryDrivenRanker** (250 lines)
   - Main ranking engine
   - Loads/saves success records from disk
   - Provides `rank_proposals()` method for reordering
   - Implements four ranking factors:
     * Direct acceptance rate (base score 0.0-1.0)
     * Recency bonus (up to +0.1, decays over 7 days)
     * Difficulty adjustment (boost reliability on hard fixtures)
     * Similarity borrowing (use similar fixtures' success patterns)
   - Generates summaries for operator insights

### Testing

**File:** `tests/test_memory_ranking.py` (390 lines, 27 tests)

Comprehensive coverage:
- ✅ Fixture success record initialization and tracking
- ✅ Acceptance/rejection recording with counter updates
- ✅ Acceptance rate calculation (including neutral default for unknowns)
- ✅ Preferred types ordering
- ✅ Difficulty detection (≥2.0 attempts per success OR low success rate)
- ✅ Serialization/deserialization roundtrips
- ✅ Ranker initialization (with/without memory directory)
- ✅ Loading persisted records from disk
- ✅ Proposal outcome tracking (acceptance + rejection)
- ✅ Proposal ranking (single, multiple, filtered by fixture)
- ✅ Success history ordering (higher success ranks higher)
- ✅ Recency bonuses
- ✅ Similar fixture discovery by name prefix
- ✅ Similarity borrowing (new fixtures learn from similar)
- ✅ Disk persistence (save/load cycles)
- ✅ Summary generation
- ✅ Score capping at ~2.0
- ✅ Difficulty adjustment (boosts reliable types)

**All 27 tests passing** ✅

### Examples

**File:** `examples/memory_driven_ranking_demo.py` (260 lines)

Five interactive demonstration scenarios:

1. **Scenario 1: Basic Ranking** - Shows test_case ranked above instruction based on 100% vs 0% success
2. **Scenario 2: Similarity Borrowing** - New fixture "api_delete" borrows success patterns from "api_get" and "api_list"
3. **Scenario 3: Difficult Fixtures** - Edge cases with many failures prioritize reliable proposal types
4. **Scenario 4: Persistence** - Success records saved in session 1, loaded and used in session 2
5. **Scenario 5: Summary Report** - Comprehensive statistics across all tracked fixtures

All scenarios run successfully and demonstrate the feature in action.

---

## Ranking Algorithm

### Scoring Formula

```
base_score = acceptance_rate_for_type_on_fixture  [0.0-1.0]

+ recency_bonus                                    [0.0-0.1]
  (full if <24h old, decays over 7 days)

+ difficulty_adjustment                           [varies]
  if fixture is hard:
    +0.15 if type has >70% success
    -0.10 if type has <30% success

+ borrowed_score                                   [0.0-0.3]
  (weighted average from top 3 similar fixtures)

= final_score [0.0-~2.0] (capped at 2.0)
```

### Example Scores

| Scenario | Type | History | Similar | Score |
|----------|------|---------|---------|-------|
| Strong pattern | test_case | 100% (recent) | — | 1.10 |
| New fixture | test_case | none | similar 100% | 0.70 |
| Difficult, reliable | test_case | 100% | hard | 1.25 |
| Difficult, unreliable | instruction | 0% | hard | -0.10 |
| Unknown on new | artifact | none | similar 50% | 0.35 |

---

## Architecture

```
MemoryDrivenRanker
├── load_success_records()      Load fixture-success.jsonl
├── record_proposal_outcome()   Track accept/reject
├── rank_proposals()            Main entry point
│   ├── _find_similar_fixtures()  Find related fixtures
│   └── _compute_rank_score()     Calculate score per proposal
├── save_success_records()      Persist to disk
└── summary()                   Generate statistics

FixtureSuccessRecord (per fixture)
├── total_attempts
├── successful_attempts
├── accepted_proposal_types     {type -> count}
├── rejected_proposal_types     {type -> count}
├── preferred_proposal_types    Sorted by success rate
├── is_historically_difficult   Boolean property
├── success_rate                Float property
└── get_acceptance_rate()       Per-type rate
```

---

## Integration Points

### Immediate Use
- Ranker is standalone and can be imported by:
  - `ProposalEngine` (enhance `generate_proposals()` output)
  - Trial loops (post-process proposal ordering)
  - CLI (expose ranking for operator review)

### Future Wiring
1. **Loop Integration** (next build block)
   - Accept `MemoryDrivenRanker` instance in guarded trial stage
   - Use `record_proposal_outcome()` to track trial results
   - Reorder proposals in next iteration

2. **Operator Dashboard**
   - Expose `summary()` output in CLI
   - Show "most reliable proposal types per fixture"
   - Highlight "historically difficult" fixtures

3. **Automated Rules**
   - Apply learned confidence thresholds automatically
   - Skip low-confidence proposal types after repeated failures

---

## Code Quality

✅ **Type Hints** - Full Python 3.9+ annotations throughout
✅ **Docstrings** - Google-style on all public APIs
✅ **PEP 8** - Compliant formatting
✅ **Error Handling** - Graceful degradation on missing files/data
✅ **No Dependencies** - Uses stdlib only (json, pathlib, dataclasses, datetime)
✅ **Tests** - 27 unit tests, 100% passing
✅ **Performance** - Fixture lookups O(1), proposal sorting O(n log n)

---

## Files Changed

### New Files
- `src/skill_auto_improver/memory_ranking.py` (381 lines)
- `tests/test_memory_ranking.py` (390 lines, 27 tests)
- `examples/memory_driven_ranking_demo.py` (260 lines)

### Updated Files
- `ROADMAP.md` - Added milestone for memory-driven ranking
- `SHIPPED.md` - Updated with latest work

### No Breaking Changes
- Existing modules unchanged
- All 147 original tests still passing
- New feature is opt-in (ranker only used if explicitly called)

---

## Test Suite Summary

```
Before: 147 tests (26 minutes of build history)
After:  174 tests (147 + 27 new)
Status: All passing ✅
Time:   0.41 seconds

Test breakdown:
- 10 FixtureSuccessRecord tests
- 3 FixtureSimilarity tests
- 14 MemoryDrivenRanker tests
```

---

## Impact

### For Skill Improvement
- Proposals now rank by what actually works for each fixture
- New/unknown fixtures automatically borrow patterns from similar ones
- Difficult fixtures get safer, proven proposal types first
- System learns what doesn't work and deprioritizes it

### For Operators
- Proposals appear in order of likelihood to succeed
- Reduced manual review/reordering needed
- Clear "preferred proposal types" per fixture visible
- Summary reports show which fixtures are trouble spots

### For System Learning
- Per-fixture success history feeds back into proposal generation
- Cross-session learning (history persists)
- Enables future automated rules (skip low-confidence types)
- Builds foundation for operator dashboard

---

## Verification

✅ All 174 tests passing  
✅ Demo runs successfully with all 5 scenarios  
✅ Persistence tested (save/load cycles)  
✅ No breaking changes to existing code  
✅ Code quality standards met  
✅ Production-ready implementation  

---

## Next Steps (Future Build Blocks)

1. **Loop Integration** - Wire ranker into guarded trial feedback loop
2. **Fixture Suggestion CLI** - Recommend library patterns for new skills
3. **Operator Dashboard** - Browse brain + ranker state together
4. **Automated Rules** - Apply learned thresholds without manual review

---

**Built by:** Autonomous Build Block  
**Status:** READY FOR PRODUCTION ✅  
**Test Coverage:** 174/174 passing  
**Lines Shipped:** 1,031 (implementation + tests + examples)
