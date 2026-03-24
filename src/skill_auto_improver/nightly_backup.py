"""
Nightly Backup Cron Job

Runs at midnight PST every night to:
1. Create dated zip of entire OpenClaw workspace (config, skills, memory, shared-brain)
2. Send zip file via Telegram with date label
3. Archive backup metadata for recovery

Triggered by: OpenClaw cron scheduler at 00:00 PST daily
Dependencies: Telegram API
Input: ~/.openclaw/workspace (full directory)
Output: Telegram file, backup metadata JSON
"""

import json
import os
import sys
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from logger import SkillAutoImproverLogger


class NightlyBackupRunner:
    """Creates and sends nightly workspace backups."""

    def __init__(self, workspace_root: str, backup_dir: Optional[str] = None,
                 telegram_token: Optional[str] = None, telegram_chat_id: Optional[str] = None,
                 max_backups: int = 30):
        """
        Initialize nightly backup runner.

        Args:
            workspace_root: Root path of OpenClaw workspace
            backup_dir: Directory to store backups (defaults to workspace/../backups/)
            telegram_token: Telegram bot token (from env if not provided)
            telegram_chat_id: Telegram chat/user ID (from env if not provided)
            max_backups: Maximum number of backups to retain (older ones deleted)
        """
        self.workspace_root = Path(workspace_root)

        # Backup directory setup
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            self.backup_dir = self.workspace_root.parent / "backups"

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Telegram credentials
        self.telegram_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.max_backups = max_backups

        # Metadata
        self.metadata_dir = self.workspace_root / "skill-auto-improver" / "runs" / "backup-metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Logger
        self.logger = SkillAutoImproverLogger(name="nightly-backup")

    def create_backup_zip(self) -> Optional[Path]:
        """
        Create dated zip file of entire workspace.

        Returns:
            Path to created zip file or None if failed
        """
        try:
            now = datetime.utcnow()
            backup_date = now.strftime("%Y-%m-%d")
            zip_filename = f"openclaw-workspace-{backup_date}.zip"
            zip_path = self.backup_dir / zip_filename

            # If backup already exists today, add timestamp
            if zip_path.exists():
                timestamp = now.strftime("%Y-%m-%d-%H%M%S")
                zip_filename = f"openclaw-workspace-{timestamp}.zip"
                zip_path = self.backup_dir / zip_filename

            self.logger.info(f"Creating backup zip at {zip_path}")

            # Create zip with compression
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Walk workspace and add all files
                for root, dirs, files in os.walk(self.workspace_root):
                    # Skip certain directories to reduce size
                    dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".pytest_cache", "node_modules"}]

                    for file in files:
                        # Skip certain files
                        if file.endswith((".pyc", ".pyo", ".log")):
                            continue

                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.workspace_root.parent)

                        try:
                            zipf.write(file_path, arcname)
                        except Exception as e:
                            self.logger.warning(f"Failed to add file to zip: {file_path} ({e})")

            # Get file size
            zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
            self.logger.info(f"Backup created successfully: {zip_filename} ({zip_size_mb:.2f} MB)")

            return zip_path

        except Exception as e:
            self.logger.error(f"Failed to create backup zip: {e}", exc_info=True)
            return None

    def send_backup_telegram(self, zip_path: Path) -> bool:
        """
        Send backup zip file via Telegram.

        Args:
            zip_path: Path to zip file

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if not self.telegram_token or not self.telegram_chat_id:
                self.logger.warning(
                    "Telegram credentials not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)"
                )
                self.logger.info(f"Backup file available at: {zip_path}")
                return False

            # Import requests here to avoid hard dependency
            try:
                import requests
            except ImportError:
                self.logger.warning("requests library not available; cannot send Telegram file")
                self.logger.info(f"Backup file available at: {zip_path}")
                return False

            # Check file size (Telegram limit is 50MB for bots)
            file_size_mb = zip_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 45:  # Conservative limit
                self.logger.warning(
                    f"Backup file too large for Telegram ({file_size_mb:.2f} MB > 45 MB limit)"
                )
                return False

            # Send via Telegram Bot API
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendDocument"
            date_label = zip_path.stem.replace("openclaw-workspace-", "")

            with open(zip_path, "rb") as f:
                files = {"document": f}
                data = {
                    "chat_id": self.telegram_chat_id,
                    "caption": f"📦 *Nightly Backup*\n\nDate: {date_label}\nSize: {file_size_mb:.2f} MB",
                    "parse_mode": "Markdown",
                }

                response = requests.post(url, data=data, files=files, timeout=60)
                response.raise_for_status()

            self.logger.info(f"Backup sent via Telegram successfully (status={response.status_code})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send backup via Telegram: {e}", exc_info=True)
            return False

    def save_backup_metadata(self, zip_path: Path, telegram_sent: bool) -> None:
        """
        Save backup metadata for recovery and auditing.

        Args:
            zip_path: Path to backup zip
            telegram_sent: Whether backup was sent via Telegram
        """
        try:
            now = datetime.utcnow()
            backup_date = now.strftime("%Y-%m-%d")
            metadata_file = self.metadata_dir / f"{backup_date}-metadata.json"

            # Build metadata
            metadata = {
                "timestamp": now.isoformat(),
                "date": backup_date,
                "filename": zip_path.name,
                "path": str(zip_path),
                "size_bytes": zip_path.stat().st_size,
                "size_mb": zip_path.stat().st_size / (1024 * 1024),
                "telegram_sent": telegram_sent,
                "workspace_root": str(self.workspace_root),
            }

            # If metadata file exists, append to array
            if metadata_file.exists():
                with open(metadata_file, "r") as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    existing.append(metadata)
                else:
                    existing = [existing, metadata]
            else:
                existing = [metadata]

            with open(metadata_file, "w") as f:
                json.dump(existing, f, indent=2)

            self.logger.info(f"Backup metadata saved to {metadata_file}")

        except Exception as e:
            self.logger.error(f"Failed to save backup metadata: {e}", exc_info=True)

    def cleanup_old_backups(self) -> None:
        """Delete backups older than max_backups retention limit."""
        try:
            # Get all backup zips sorted by modification time
            backup_files = sorted(
                self.backup_dir.glob("openclaw-workspace-*.zip"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            # Delete if more than max_backups
            for old_backup in backup_files[self.max_backups:]:
                try:
                    old_backup.unlink()
                    self.logger.info(f"Deleted old backup: {old_backup.name}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete old backup {old_backup.name}: {e}")

        except Exception as e:
            self.logger.error(f"Cleanup of old backups failed: {e}", exc_info=True)

    def run(self) -> bool:
        """
        Execute full nightly backup workflow.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("=" * 80)
        self.logger.info("NIGHTLY BACKUP STARTING")
        self.logger.info("=" * 80)

        try:
            # 1. Create backup zip
            zip_path = self.create_backup_zip()
            if not zip_path:
                self.logger.error("Failed to create backup zip; exiting")
                return False

            # 2. Send via Telegram (best effort)
            telegram_sent = self.send_backup_telegram(zip_path)

            # 3. Save metadata
            self.save_backup_metadata(zip_path, telegram_sent)

            # 4. Cleanup old backups
            self.cleanup_old_backups()

            # 5. Final log
            self.logger.info("=" * 80)
            self.logger.info("NIGHTLY BACKUP COMPLETE")
            self.logger.info(f"Backup available at: {zip_path}")
            self.logger.info(f"Telegram sent: {telegram_sent}")
            self.logger.info("=" * 80)

            return True

        except Exception as e:
            self.logger.error(f"Nightly backup failed: {e}", exc_info=True)
            return False


def main():
    """Entry point for nightly backup cron job."""
    workspace_root = os.getenv("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace"))

    runner = NightlyBackupRunner(workspace_root)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
