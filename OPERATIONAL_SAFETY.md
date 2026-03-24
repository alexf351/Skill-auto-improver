# Operational Safety & Data Retention

This document outlines the operational policies, data retention, backup procedures, and rollback capabilities for skill-auto-improver.

---

## Data Retention Policy

### Run Logs (Default: 30 Days)

**Location:** `~/.openclaw/workspace/.logs/`

**Retention:** 30 days by default (configurable)

**Log files:**
- `run_observe_*.log` — Skill behavior observation
- `run_inspect_*.log` — Failure analysis & proposals
- `run_amend_*.log` — Patch application & testing
- `run_evaluate_*.log` — Before/after comparison metrics
- `run_execute_*.log` — Subprocess stdout/stderr

**Automatic cleanup:**
```bash
# Run via cron (daily)
$ skill-auto-improver cleanup-logs --older-than 30d

# Manual cleanup
$ python -c "from skill_auto_improver.logger import cleanup_logs; cleanup_logs(days=30)"
```

**What happens:**
1. Finds all `run_*.log` files modified >30 days ago
2. Compresses to `run_logs_archive_2026-03-01.zip`
3. Moves to archive directory
4. Deletes uncompressed originals
5. Logs cleanup action with count

---

### Backup Files (Default: 60 Days)

**Location:** `~/.openclaw/workspace/.backups/`

**Retention:** 60 days by default (configurable)

**Backup files:**
- `skill-name-TIMESTAMP.zip` — Complete skill snapshot (before patch)
- `metadata.json` — Backup metadata (skill_path, timestamp, reason)

**Example backup structure:**
```
.backups/
  my-skill-2026-03-24_10-15-27.zip
    └── SKILL.md (original)
    └── src/ (original)
    └── metadata.json
  my-skill-2026-03-20_14-32-15.zip
    └── SKILL.md (original)
    └── src/ (original)
    └── metadata.json
```

**Automatic cleanup:**
```bash
# Run via cron (daily)
$ skill-auto-improver cleanup-backups --older-than 60d

# Manual cleanup
$ python -c "from skill_auto_improver.applier import cleanup_backups; cleanup_backups(days=60)"
```

**What happens:**
1. Finds all `skill-*-TIMESTAMP.zip` files older than 60 days
2. Verifies backup integrity (checksums)
3. Deletes old backups
4. Logs cleanup with count and freed space

---

## Backup & Restore Procedures

### Creating a Backup (Automatic)

**Triggered before any AMEND operation:**

```python
# In applier.py → _safe_amend_skill()
def _safe_amend_skill(self, skill_path, proposals):
    # ✅ Create backup BEFORE write
    backup = self._create_backup(skill_path)
    logger.info(f"Backup created: {backup.path}")
    
    # Now safe to write
    self._apply_patches_to_skill_md(skill_path, proposals)
```

**Backup contents:**
- Complete SKILL.md (original)
- All source files (if modifying src/)
- Metadata file (timestamp, skill path, reason)
- Checksum for integrity verification

**Example backup metadata:**
```json
{
  "skill_path": "/home/user/.openclaw/workspace/my-skill",
  "timestamp": "2026-03-24T10:15:27Z",
  "reason": "pre_amend",
  "checksum_md5": "abc123def456...",
  "size_bytes": 45678,
  "files_included": [
    "SKILL.md",
    "src/my_skill.py"
  ]
}
```

### Restoring from Backup

**Manual restore:**

```bash
# List available backups
$ skill-auto-improver list-backups --skill my-skill

# Restore a specific backup
$ skill-auto-improver restore-backup \
    --skill my-skill \
    --backup 2026-03-24_10-15-27

# Restore latest backup
$ skill-auto-improver restore-backup --skill my-skill --latest
```

**Automated restore (on test failure):**

```python
# In applier.py → _test_amended_skill()
if test_result.failed:
    logger.error("Amended skill failed testing, auto-rolling back...")
    self._restore_backup(backup.path)
    return ApplyReport(status="rollback", reason="test_failed")
```

**Restore operation:**
1. Verify backup integrity (checksum match)
2. Read backup ZIP
3. Extract files to original locations
4. Verify file ownership/permissions match original
5. Log restore with timestamp and reason

---

## Cron Schedule (Recommended)

Run these periodic maintenance tasks:

```bash
# Add to crontab (daily)
0 2 * * * /usr/local/bin/skill-auto-improver cleanup-logs --older-than 30d
0 3 * * * /usr/local/bin/skill-auto-improver cleanup-backups --older-than 60d

# Add to crontab (weekly, Sunday 1 AM)
0 1 * * 0 /usr/local/bin/skill-auto-improver verify-backups

# Add to crontab (nightly, if running autonomous improvements)
0 2 * * * /usr/local/bin/skill-auto-improver nightly-orchestrator
```

---

## Rollback Procedures

### Automatic Rollback (On Test Failure)

**When it happens:**
- Patch applied → Skill tested (30s timeout)
- Test fails (non-zero exit code)
- **Automatic rollback triggered**

**What happens:**
```python
if proc.returncode != 0:
    logger.critical("Test failed, rolling back to pre-amend state")
    backup.restore()  # ← Automatic
    run_trace.add_step(
        name="rollback",
        status="success",
        metadata={"reason": "test_failed", "backup_used": backup.path}
    )
```

**Result:**
- SKILL.md restored to pre-patch version
- All files restored from backup
- Loop continues to next iteration or stops
- User notified via logs

### User-Initiated Rollback

**When to use:**
- Skill behaving unexpectedly in production
- Need to revert to known-good state
- Investigating regression

**How to trigger:**
```bash
# Roll back to most recent successful state
$ skill-auto-improver rollback --skill my-skill --reason "production_issue"

# Roll back to specific backup
$ skill-auto-improver rollback --skill my-skill --backup 2026-03-23_15-30-00

# Dry-run (show what would be rolled back)
$ skill-auto-improver rollback --skill my-skill --dry-run
```

**Rollback safety checks:**
1. Backup must exist and be uncorrupted
2. Checksum verified before restore
3. Original state backed up (backup-of-backup)
4. Git history preserved (no destructive git resets)

---

## Integrity Verification

### Backup Integrity Checks

**Automatic (weekly via cron):**
```bash
$ skill-auto-improver verify-backups

# Output:
# 2026-03-24 03:00:00 [INFO] Verifying 12 backups...
# 2026-03-24 03:00:01 [OK] my-skill-2026-03-24_10-15-27.zip (checksum: ok)
# 2026-03-24 03:00:02 [OK] other-skill-2026-03-20_14-32-15.zip (checksum: ok)
# 2026-03-24 03:00:03 [PASS] All 12 backups verified successfully
```

**Manual verification:**
```python
from skill_auto_improver.applier import SkillPatchApplier

applier = SkillPatchApplier(workspace="/path/to/workspace")
report = applier.verify_backup("/path/to/backup.zip")

print(f"Status: {report.status}")  # "ok" or "corrupted"
print(f"Checksum: {report.checksum_match}")  # True/False
print(f"File count: {report.file_count}")  # Number of files in backup
```

### Run History Integrity

**Check that logs haven't been tampered with:**
```bash
# Verify all run traces are valid JSON
$ skill-auto-improver verify-traces --after 2026-03-20

# Output:
# 2026-03-24 10:15:27 [TRACE] run_observe_2026-03-24_10-15-23.log: valid ✓
# 2026-03-24 10:15:28 [TRACE] run_inspect_2026-03-24_10-15-24.log: valid ✓
# 2026-03-24 10:15:29 [TRACE] run_amend_2026-03-24_10-15-25.log: valid ✓
# All traces verified: 127 logs, 0 errors
```

---

## Disaster Recovery

### Scenario 1: Corrupted SKILL.md in Production

**Symptoms:**
- Skill throwing errors
- Recent amend suspected to be cause

**Recovery:**
```bash
# 1. Identify most recent successful patch
$ skill-auto-improver list-backups --skill my-skill

# 2. Get before/after diff
$ skill-auto-improver show-diff \
    --backup 2026-03-24_10-15-27 \
    --current

# 3. Review diff and approve rollback
$ skill-auto-improver rollback \
    --skill my-skill \
    --backup 2026-03-23_15-30-00 \
    --reason "corrupted_skill_md_in_production"

# 4. Verify rollback
$ skill-auto-improver verify-skill --skill my-skill
```

### Scenario 2: Lost Backups

**Symptoms:**
- Backup directory deleted
- Cannot restore from backup

**Recovery (limited):**
```bash
# 1. Check git history
$ cd /path/to/skill
$ git log --oneline SKILL.md | head -10
# 2026-03-24_10-15-27 [AUTO-AMEND] Fixed step 2 handling
# 2026-03-24_10-15-00 [AUTO-AMEND] Initial structure
# 2026-03-20_14-32-15 Manual edit

# 2. Restore from git if available
$ git checkout 2026-03-20_14-32-15 -- SKILL.md

# 3. If git not available, cannot recover (maintain backups!)
```

**Prevention:**
- Enable git version control for all skills
- Run `skill-auto-improver verify-backups` weekly
- Test restore procedure monthly
- Keep off-site backup copies (S3, etc.)

### Scenario 3: Run History Truncated

**Symptoms:**
- Cannot audit what happened
- Logs deleted or corrupted

**Recovery:**
```bash
# 1. Restore from log archive
$ skill-auto-improver restore-logs --archive run_logs_archive_2026-03-01.zip

# 2. Re-verify git history for skill changes
$ git log --all --decorate --oneline

# 3. Reconstruct timeline from timestamps
```

---

## Monitoring & Alerting

### Health Checks (Optional)

```bash
# Run regular health check
$ skill-auto-improver health-check

# Output:
# [OK] Backups exist: 12 backups, latest: 2026-03-24_10-15-27
# [OK] Logs exist: 145 logs, oldest: 2026-02-20_14-32-15
# [OK] Backup integrity: 12/12 verified ✓
# [OK] Trace integrity: 145/145 valid ✓
# [WARNING] Backups >60d will be deleted: 3 backups
# [WARNING] Logs >30d will be deleted: 18 logs
# Overall: HEALTHY
```

### Alerting (Custom Integration)

Can integrate with monitoring systems:

```python
# Example: Send alerts on rollback
from skill_auto_improver.logger import listen_for_events

for event in listen_for_events():
    if event.type == "rollback":
        # Send alert to Slack, PagerDuty, etc.
        notify_alert(f"Skill {event.skill} rolled back: {event.reason}")
```

---

## Retention Policy Summary

| Data Type | Default Retention | Purpose | Cleanup |
|-----------|-------------------|---------|---------|
| Run logs | 30 days | Audit trail | Auto-archived |
| Backups | 60 days | Recovery | Auto-deleted |
| Git history | Forever | Version control | Manual |
| Evaluation metrics | 30 days | Performance tracking | Auto-deleted |
| Approval records | 60 days | Accountability | Auto-deleted |

---

## Testing the Safety Model

```bash
# Test backup creation
$ python -m pytest tests/test_applier.py::test_backup_created_before_amend -v

# Test automatic rollback on failure
$ python -m pytest tests/test_applier.py::test_rollback_on_test_failure -v

# Test restore integrity
$ python -m pytest tests/test_applier.py::test_restore_checksum_verified -v

# Test log cleanup
$ python -m pytest tests/test_logger.py::test_cleanup_logs_deletes_old_files -v

# Integration test: amend → fail → rollback → verify
$ python -m pytest tests/test_integration.py::test_full_rollback_cycle -v
```

---

## Configuration

### Via Environment Variables

```bash
export SKILL_LOG_RETENTION_DAYS=30
export SKILL_BACKUP_RETENTION_DAYS=60
export SKILL_EXECUTION_TIMEOUT_SECONDS=30
export SKILL_BACKUP_DIR="/custom/backup/path"
```

### Via Config File

```yaml
# ~/.openclaw/skill-auto-improver.yml
retention:
  logs:
    days: 30
    archive: true
  backups:
    days: 60
    verify_weekly: true

execution:
  timeout: 30  # seconds
  subprocess_env_whitelist:
    - PYTHONPATH
    - SKILL_PATH

backup:
  destination: "/mnt/backup/skills"
  compress: true
```

---

## Questions & Support

For questions about operational safety, backup procedures, or disaster recovery:
1. Review this document
2. Check CODE_AUDIT_GUIDE.md for execution isolation details
3. Review logs in `~/.openclaw/workspace/.logs/`
4. Run `skill-auto-improver health-check` to diagnose issues
