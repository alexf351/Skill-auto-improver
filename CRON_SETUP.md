# Nightly Operational Crons Setup Guide

This document describes how to configure the three nightly operational cron jobs for skill-auto-improver.

## Overview

Three cron jobs run automatically to keep skill-auto-improver operational:

| Job | Time (PST) | Purpose | Input | Output |
|-----|-----------|---------|-------|--------|
| **Nightly Orchestrator** | 2:00 AM | Run multi-skill improvement trials | 5 installed skills | `run-history.jsonl`, `morning-summary.json` |
| **Morning Summary Sender** | 7:00 AM | Send morning brief to Telegram | `morning-summary.json` | Telegram message, archive |
| **Nightly Backup** | 12:00 AM (midnight) | Backup entire workspace | `~/.openclaw/workspace` | Backup zip, metadata JSON |

## Prerequisites

### 1. Environment Variables

Set these environment variables in your OpenClaw environment:

```bash
# Workspace root (optional, defaults to ~/.openclaw/workspace)
export OPENCLAW_WORKSPACE="/home/clawd/.openclaw/workspace"

# Telegram Bot Credentials (required for sending Telegram messages)
export TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
export TELEGRAM_CHAT_ID="your-telegram-chat-id"
```

### 2. Telegram Bot Setup

If you don't have a Telegram bot:

1. Open Telegram and find [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Save the bot token (looks like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
4. Get your chat ID:
   - Message your bot
   - Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Find your user ID in the response

### 3. Installed Skills

Verify that the 5 monitored skills are installed:

```bash
ls ~/.openclaw/workspace/skills/ | grep -E "(morning-brief|weather-brief|kiro-dev-assistant|kiro-content-calendar|kiro-ugc-brief)"
```

All 5 should be present:
- `morning-brief` ✅
- `weather-brief` ✅
- `kiro-dev-assistant` ✅
- `kiro-content-calendar` ✅
- `kiro-ugc-brief` ✅

## Configuration

### Option 1: OpenClaw Cron Scheduler (Recommended)

If using OpenClaw's built-in cron scheduler:

```bash
# Register nightly orchestrator (2 AM PST)
openclaw cron add \
  --name "skill-auto-improver-nightly-orchestrator" \
  --schedule "0 2 * * *" \
  --timezone "America/Los_Angeles" \
  --command "python ~/.openclaw/workspace/skill-auto-improver/src/skill_auto_improver/nightly_orchestrator.py"

# Register morning summary sender (7 AM PST)
openclaw cron add \
  --name "skill-auto-improver-morning-summary" \
  --schedule "0 7 * * *" \
  --timezone "America/Los_Angeles" \
  --command "python ~/.openclaw/workspace/skill-auto-improver/src/skill_auto_improver/morning_summary_sender.py"

# Register nightly backup (midnight PST)
openclaw cron add \
  --name "skill-auto-improver-nightly-backup" \
  --schedule "0 0 * * *" \
  --timezone "America/Los_Angeles" \
  --command "python ~/.openclaw/workspace/skill-auto-improver/src/skill_auto_improver/nightly_backup.py"
```

### Option 2: System Crontab

If running on a Linux/macOS system with crontab:

```bash
# Edit crontab
crontab -e
```

Add these lines (adjust timezone if not PST):

```cron
# Nightly Backup (midnight PST = 8 AM UTC)
0 8 * * * cd ~/.openclaw/workspace && OPENCLAW_WORKSPACE=~/.openclaw/workspace TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID python src/skill_auto_improver/nightly_backup.py 2>&1 >> ~/.openclaw/workspace/skill-auto-improver/logs/nightly-backup.log

# Nightly Orchestrator (2 AM PST = 10 AM UTC)
0 10 * * * cd ~/.openclaw/workspace && OPENCLAW_WORKSPACE=~/.openclaw/workspace python src/skill_auto_improver/nightly_orchestrator.py 2>&1 >> ~/.openclaw/workspace/skill-auto-improver/logs/nightly-orchestrator.log

# Morning Summary Sender (7 AM PST = 3 PM UTC)
0 15 * * * cd ~/.openclaw/workspace && OPENCLAW_WORKSPACE=~/.openclaw/workspace TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID python src/skill_auto_improver/morning_summary_sender.py 2>&1 >> ~/.openclaw/workspace/skill-auto-improver/logs/morning-summary.log
```

Create log directory:

```bash
mkdir -p ~/.openclaw/workspace/skill-auto-improver/logs
```

## Output Locations

### Nightly Orchestrator
- **History:** `~/.openclaw/workspace/skill-auto-improver/runs/run-history.jsonl`
- **Morning Summary:** `~/.openclaw/workspace/skill-auto-improver/runs/morning-summary.json`
- **Logs:** `~/.openclaw/workspace/skill-auto-improver/logs/nightly-orchestrator.log`

### Morning Summary Sender
- **Archive:** `~/.openclaw/workspace/skill-auto-improver/runs/archive/YYYY-MM-DD-summary.json`
- **Logs:** `~/.openclaw/workspace/skill-auto-improver/logs/morning-summary.log`
- **Telegram:** Direct message to configured chat

### Nightly Backup
- **Backups:** `~/.openclaw/backups/openclaw-workspace-YYYY-MM-DD.zip`
- **Metadata:** `~/.openclaw/workspace/skill-auto-improver/runs/backup-metadata/YYYY-MM-DD-metadata.json`
- **Logs:** `~/.openclaw/workspace/skill-auto-improver/logs/nightly-backup.log`
- **Telegram:** File upload to configured chat

## Manual Execution

Run any job manually for testing:

```bash
# Test nightly orchestrator
python ~/.openclaw/workspace/skill-auto-improver/src/skill_auto_improver/nightly_orchestrator.py

# Test morning summary sender
python ~/.openclaw/workspace/skill-auto-improver/src/skill_auto_improver/morning_summary_sender.py

# Test nightly backup
python ~/.openclaw/workspace/skill-auto-improver/src/skill_auto_improver/nightly_backup.py
```

## Monitoring

### Check Cron Status

**OpenClaw Cron:**
```bash
openclaw cron list
openclaw cron status skill-auto-improver-nightly-orchestrator
```

**System Crontab:**
```bash
crontab -l | grep skill-auto-improver
```

### View Logs

```bash
# Tail recent logs
tail -f ~/.openclaw/workspace/skill-auto-improver/logs/nightly-*.log

# View run history
cat ~/.openclaw/workspace/skill-auto-improver/runs/run-history.jsonl | jq .

# View morning summary archive
ls -la ~/.openclaw/workspace/skill-auto-improver/runs/archive/
```

## Troubleshooting

### Cron Jobs Not Running

1. **Check environment variables:**
   ```bash
   echo $OPENCLAW_WORKSPACE
   echo $TELEGRAM_BOT_TOKEN
   ```

2. **Check logs:**
   ```bash
   tail -20 ~/.openclaw/workspace/skill-auto-improver/logs/*.log
   ```

3. **Test Python path:**
   ```bash
   cd ~/.openclaw/workspace
   python -c "from skill_auto_improver import nightly_orchestrator; print('Import OK')"
   ```

### Telegram Messages Not Sending

1. **Verify credentials:**
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
   ```

2. **Test bot access:**
   - Ensure bot has permission to message the chat ID
   - Try sending a test message manually to the bot

3. **Check logs for error details:**
   ```bash
   grep -i "telegram" ~/.openclaw/workspace/skill-auto-improver/logs/*.log
   ```

### Backup File Too Large

If backup exceeds Telegram's 50 MB limit:

1. **Exclude files:** Edit `nightly_backup.py` to skip large directories
2. **Upload manually:** Store backup locally only, sync to cloud separately
3. **Compress more:** Use lower compression level if needed

## Scheduling Reference

### PST to UTC Conversion

- 12:00 AM PST (Backup) = **8:00 AM UTC**
- 2:00 AM PST (Orchestrator) = **10:00 AM UTC**
- 7:00 AM PST (Summary) = **3:00 PM UTC**

### Cron Schedule Format

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
│ │ │ │ │
* * * * *
```

Examples:
- `0 2 * * *` = Every day at 2 AM
- `0 0 * * *` = Every day at midnight
- `0 7 * * MON-FRI` = Every weekday at 7 AM
- `*/30 * * * *` = Every 30 minutes

## Best Practices

1. **Timezone Consistency:** Always use PST/America/Los_Angeles for all cron jobs
2. **Log Rotation:** Set up log rotation for long-running deployments:
   ```bash
   # Add to crontab
   0 3 * * * find ~/.openclaw/workspace/skill-auto-improver/logs -name "*.log" -mtime +7 -delete
   ```
3. **Backup Verification:** Periodically test restore from backup:
   ```bash
   # List contents of latest backup
   unzip -l ~/.openclaw/backups/openclaw-workspace-*.zip | tail -20
   ```
4. **Monitoring Dashboard:** Check `run-history.jsonl` and archive summaries weekly
5. **Telegram Alerts:** Consider adding error-only alerts for critical failures

## Next Steps

1. ✅ Set up environment variables
2. ✅ Verify Telegram bot credentials
3. ✅ Confirm all 5 skills are installed
4. ✅ Register cron jobs via OpenClaw or system crontab
5. ✅ Test manually each job
6. ✅ Monitor logs and Telegram for first week
7. ✅ Set up log rotation after 7 days

## Support

For issues or questions:
- Check logs in `~/.openclaw/workspace/skill-auto-improver/logs/`
- Review `run-history.jsonl` for execution history
- Examine Telegram message archives for summary format
- Test individual jobs manually with verbose output

---

**Last Updated:** 2026-03-24  
**Version:** 1.0  
**Status:** Ready for Deployment
