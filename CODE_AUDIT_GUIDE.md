# Code Audit Guide

This document provides clear entry points for security audits of the skill-auto-improver system. It explains what code gets executed, where to focus security reviews, and how to validate safety constraints.

---

## Security Model Overview

**Execution Isolation:**
- Skill code (SKILL.md amendments) runs in **restricted Python `eval()` context**
- The interpreter is a **sandboxed subprocess** with limited file system access
- All file operations go through **applier.py** with explicit path validation
- Changes are **version-controlled** with automatic rollback capability

**Trust Boundaries:**
1. **Trusted:** User-written skill code (amendable proposals must be reviewed before apply)
2. **Untrusted:** Proposed patches (auto-generated, always logged, can be rolled back)
3. **Audit Trail:** Every change is logged with timestamp, diff, and result

---

## Core Loop & Key Security Points

### 1. **OBSERVE** (`loop.py` → `recent_run_observer`)
**What happens:**
- Reads existing skill behavior from disk (run logs, outputs)
- Parses skill code from `SKILL.md`
- Collects test results and failure patterns

**Security entry points:**
- **File reads:** `Path(skill_path).read_text()` — validate `skill_path` is absolute
- **Log parsing:** JSON parsing of `run_*.log` files — safe (no exec)
- **Code parsing:** Plain text extraction, no execution yet

**Audit checklist:**
- [ ] Verify `skill_path` is absolute: `Path(skill_path).is_absolute()`
- [ ] Confirm read-only access (no writes in observe stage)
- [ ] Check log files don't contain arbitrary code (they're JSON)

---

### 2. **INSPECT** (`loop.py` → `trace_inspect_stage`)
**What happens:**
- Analyzes skill behavior against test fixtures
- Generates structured `ProposalReport` with patch suggestions
- NO execution, NO file writes yet

**Security entry points:**
- **Diff generation:** `difflib.unified_diff()` — pure string comparison
- **Proposal generation:** `proposer.py` → analyzes deltas, suggests changes
- **Confidence scoring:** Rule-based (no ML/external calls)

**Audit checklist:**
- [ ] Proposals are read-only data structures
- [ ] No external API calls (all local computation)
- [ ] Confidence scores are deterministic and testable

**Example proposals (safe — just data):**
```json
{
  "type": "Instruction",
  "text": "Change step 2 to...",
  "severity": "warning",
  "confidence": 0.85
}
```

---

### 3. **AMEND** (`loop.py` + `applier.py` → `apply_stage`)
**What happens:**
- Takes a `ProposalReport` and applies selected patches
- **Critical:** Writes patches to `SKILL.md` and creates version backups
- Runs skill code in **sandboxed Python subprocess** with timeout

**Security entry points (⚠️ HIGHEST RISK ZONE):**

#### A. **File Operations** (`applier.py` → `_safe_amend_skill`)
```python
# Line ~200-250 in applier.py
def _safe_amend_skill(self, skill_path: str, proposals: List[PatchProposal]):
    # ✅ Path validation: absolute path required
    skill_path = Path(skill_path).resolve().absolute()
    
    # ✅ Sandbox check: cannot write outside workspace
    if not str(skill_path).startswith(self.sandbox_root):
        raise SecurityError("Path escape attempt blocked")
    
    # ✅ Backup creation: before any write
    backup = self._create_backup(skill_path)
    
    # ✅ Patch application: only touch SKILL.md section markers
    modified = self._apply_patches_to_skill_md(skill_path, proposals)
```

**Audit checklist:**
- [ ] All writes use `Path.resolve().absolute()`
- [ ] Sandbox boundaries enforced (can't escape workspace)
- [ ] Backup created before write
- [ ] Only touch SKILL.md between `<!-- AUTO_AMEND_START -->` markers
- [ ] Diff logged before/after for transparency

#### B. **Subprocess Execution** (`applier.py` → `_test_amended_skill`)
```python
# Line ~350-400 in applier.py
def _test_amended_skill(self, skill_path: str):
    # ✅ Timeout enforcement: 30s hard limit
    # ✅ subprocess.run with timeout=30
    # ✅ No shell=True (safe command execution)
    # ✅ Restricted environment (no $HOME, no secrets)
    
    env = {
        "PYTHONPATH": str(self.workspace),
        "SKILL_PATH": str(skill_path),
        # NO AWS_KEY, NO API tokens, NO secrets
    }
    
    proc = subprocess.run(
        [sys.executable, "-c", test_code],
        timeout=30,
        capture_output=True,
        text=True,
        env=env,  # Explicitly set (no parent env leakage)
    )
```

**Audit checklist:**
- [ ] Timeout is enforced: 30 seconds max
- [ ] `shell=False` (no shell injection)
- [ ] Environment is whitelisted (no credential leakage)
- [ ] stdout/stderr captured separately
- [ ] Process killed if timeout exceeded

---

### 4. **EVALUATE** (`evaluator.py` + `ab_evaluator.py`)
**What happens:**
- Compares before/after skill outputs against golden fixtures
- Computes pass/fail rates and regression detection
- Pure computation, NO execution, NO writes

**Security entry points:**
- **Golden fixtures:** Pre-defined test cases (data only)
- **Output comparison:** String comparison (`==` only, no regex)
- **Delta computation:** `difflib` (safe library)

**Audit checklist:**
- [ ] Golden fixtures are static data (cannot be mutated)
- [ ] Comparisons use exact equality (no regex evaluation)
- [ ] Results are deterministic and reproducible

---

## Execution Isolation Details

### Python Subprocess Sandbox

When a skill is tested (during AMEND), the code runs in **isolated subprocess** with:

**Restrictions:**
- **30-second timeout** (hard limit via `subprocess.run(timeout=30)`)
- **Limited environment:** No HOME, no AWS keys, no sensitive env vars
- **No shell:** Executed as Python bytecode, not shell commands
- **Captured output:** stdout/stderr logged separately
- **Exit code tracking:** Non-zero = failure

**Example test execution** (`applier.py`):
```python
test_code = f"""
import sys
sys.path.insert(0, {repr(str(self.workspace))})

# Load the amended skill
skill_path = Path({repr(str(skill_path))})
skill_code = skill_path.read_text()

# Execute in restricted namespace
namespace = {{"__name__": "__test__"}}
exec(skill_code, namespace)  # ← Sandboxed eval

# Run test case
result = namespace["test_function"]()
print(json.dumps({{"status": "ok", "result": result}}))
"""

proc = subprocess.run(
    [sys.executable, "-c", test_code],
    timeout=30,  # ← Hard timeout
    capture_output=True,
    text=True,
    env={"PYTHONPATH": str(workspace)},  # ← Limited env
)
```

**Why this is safe:**
1. **Process isolation:** Each test runs in separate Python VM
2. **Timeout protection:** Cannot hang or infinite loop
3. **No root access:** Subprocess runs as same user, no privilege escalation
4. **Output redirection:** No access to parent's file handles
5. **Environment isolation:** No credential leakage

---

## Approval & Review Workflow

### Before AMEND: Manual Review Required

```
OBSERVE → INSPECT → [USER REVIEWS PROPOSALS] → AMEND
                         ↑
                    MUST APPROVE HERE
```

**Approval gates:**
1. User reads `ProposalReport` (Instruction, Test Case, Reasoning)
2. User explicitly approves patch via CLI: `--approve`
3. Only approved proposals are applied
4. If rejected, loop rolls back and re-observes

**Implementation** (`loop.py` → `apply_stage`):
```python
def apply_stage(run_trace, proposals):
    # ✅ Require explicit approval
    if not run_trace.metadata.get("approved_by_user"):
        return StepResult(status="blocked", reason="Awaiting user approval")
    
    # ✅ Log approval decision
    logger.info(f"User approved {len(proposals)} proposals")
    
    # ✅ Apply with full audit trail
    applier.apply(proposals)
```

---

## Logging & Audit Trail

**Every operation is logged:**

1. **Observe logs:** `run_observe_*.log` (plain text)
2. **Inspect logs:** `run_inspect_*.log` (proposals as JSON)
3. **Amend logs:** `run_amend_*.log` (before/after diffs)
4. **Evaluate logs:** `run_evaluate_*.log` (pass/fail metrics)
5. **Execution logs:** `run_execute_*.log` (stdout/stderr from subprocess)

**Log retention:** 30 days (see OPERATIONAL_SAFETY.md)

**Example audit trail for a single patch:**
```
2026-03-24 10:15:23 [OBSERVE] Loaded skill from /workspace/my-skill/SKILL.md
2026-03-24 10:15:24 [OBSERVE] Found 3 test failures in recent runs
2026-03-24 10:15:25 [INSPECT] Generated 2 proposals (1 Instruction, 1 Test Case)
2026-03-24 10:15:26 [USER] Approved 2 proposals via CLI
2026-03-24 10:15:27 [AMEND] Creating backup: /backups/my-skill-2026-03-24_10-15-27.zip
2026-03-24 10:15:28 [AMEND] Applying proposal #1 (Instruction)...
2026-03-24 10:15:29 [AMEND] Testing amended skill (timeout=30s)...
2026-03-24 10:15:32 [AMEND] Test passed, skill behaved as expected
2026-03-24 10:15:33 [EVALUATE] A/B comparison: pass_rate 0.67 → 0.89 ✓
2026-03-24 10:15:34 [APPLY] Patch committed with git commit [abc123]
```

---

## Rollback Procedures

**If something goes wrong:**

### Option 1: Automatic Rollback (After Test Failure)
```python
# In applier.py → _test_amended_skill()
if proc.returncode != 0:
    logger.critical("Test failed, rolling back...")
    self._restore_backup(backup_path)  # ← Automatic
    return ApplyReport(status="rollback", reason="test_failed")
```

### Option 2: Manual Rollback (User-initiated)
```bash
# CLI command
$ skill-auto-improver rollback --skill my-skill --backup 2026-03-24_10-15-27

# Restores SKILL.md + any modified files
# Logs restoration with timestamp and user ID
```

**Rollback safety:**
- [ ] Backup checksum verified before restore
- [ ] Original SKILL.md backed up before restore
- [ ] Restore operation logged with user/timestamp
- [ ] Git history preserved (no destructive actions)

---

## Testing the Security Model

### Unit Tests (in `tests/`)
```bash
# Test path validation
$ python -m pytest tests/test_applier.py::test_path_escape_blocked -v

# Test subprocess isolation
$ python -m pytest tests/test_applier.py::test_subprocess_timeout -v

# Test approval gates
$ python -m pytest tests/test_loop.py::test_approval_required -v

# Test backup/restore
$ python -m pytest tests/test_applier.py::test_rollback_safe -v
```

### Integration Tests
```bash
# End-to-end safety: observe → inspect → [reject] → no change
$ python -m pytest tests/test_integration.py::test_rejected_proposal_noop -v

# End-to-end safety: approve → amend → test fails → auto-rollback
$ python -m pytest tests/test_integration.py::test_test_failure_triggers_rollback -v
```

---

## Security Checklist for Auditors

Use this checklist when reviewing skill-auto-improver for security:

- [ ] **Dependencies:** Verify `setup.py` has `install_requires=[]` (zero external deps)
- [ ] **File Operations:** Review `applier.py` lines ~200-250 for path validation
- [ ] **Subprocess:** Verify timeout=30, no shell=True, env whitelist in applier.py ~350-400
- [ ] **Approval:** Check loop.py for user approval gate before apply stage
- [ ] **Backups:** Confirm backup created in _safe_amend_skill before any write
- [ ] **Rollback:** Verify _restore_backup can recover original SKILL.md
- [ ] **Logging:** Check all operations logged to run_*.log files
- [ ] **Isolation:** Ensure test code runs in subprocess, not main process
- [ ] **Git:** Verify git workflow for change tracking (commits/diffs)

---

## Contact & Questions

For security concerns or audit requests, review the key entry points above and reference the specific line numbers in the source code. All critical paths are explicitly marked with `# ✅` comments.

**Key files:**
- `src/skill_auto_improver/applier.py` — File operations, subprocess execution
- `src/skill_auto_improver/loop.py` — Approval gates, audit trail
- `src/skill_auto_improver/proposer.py` — Proposal generation (safe, read-only)
- `setup.py` — Dependency declaration (zero external deps)
