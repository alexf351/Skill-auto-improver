"""
Morning Summary Telegram Sender

Runs at 7 AM PST every morning to:
1. Read morning-summary.json prepared by nightly orchestrator
2. Format summary into human-readable Telegram message
3. Send via Telegram to configured channel/user
4. Archive sent summary with timestamp

Triggered by: OpenClaw cron scheduler at 07:00 PST daily
Dependencies: nightly_orchestrator.py (prepares morning-summary.json)
Input: morning-summary.json
Output: Telegram message, archive/YYYY-MM-DD-summary.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from logger import SkillAutoImproverLogger


class MorningSummarySender:
    """Sends formatted morning summary to Telegram."""

    def __init__(self, workspace_root: str, telegram_token: Optional[str] = None, 
                 telegram_chat_id: Optional[str] = None):
        """
        Initialize morning summary sender.

        Args:
            workspace_root: Root path of OpenClaw workspace
            telegram_token: Telegram bot token (from env if not provided)
            telegram_chat_id: Telegram chat/user ID (from env if not provided)
        """
        self.workspace_root = Path(workspace_root)
        self.skill_auto_improver_root = self.workspace_root / "skill-auto-improver"
        self.morning_summary_path = self.skill_auto_improver_root / "runs" / "morning-summary.json"
        self.archive_dir = self.skill_auto_improver_root / "runs" / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Telegram credentials from env
        self.telegram_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")

        # Logger
        self.logger = SkillAutoImproverLogger(name="morning-summary-sender")

    def load_summary(self) -> Optional[Dict[str, Any]]:
        """
        Load morning summary from file.

        Returns:
            Dict with summary data or None if not found
        """
        try:
            if not self.morning_summary_path.exists():
                self.logger.warning(f"Morning summary not found at {self.morning_summary_path}")
                return None

            with open(self.morning_summary_path, "r") as f:
                summary = json.load(f)

            self.logger.info(f"Loaded morning summary from {self.morning_summary_path}")
            return summary
        except Exception as e:
            self.logger.error(f"Failed to load morning summary: {e}", exc_info=True)
            return None

    def format_message(self, summary: Dict[str, Any]) -> str:
        """
        Format summary into human-readable Telegram message.

        Args:
            summary: Dict with summary data

        Returns:
            Formatted message string
        """
        try:
            run_id = summary.get("run_id", "unknown")
            period = summary.get("period", "nightly")

            # Improvements section
            improvements = summary.get("improvements", {})
            skills_improved = improvements.get("skills_improved", 0)
            total_trials = improvements.get("total_trials", 0)

            # Blocks section
            blocks = summary.get("blocks", {})
            failed_skills = blocks.get("failed_skills", [])
            errors = blocks.get("error_messages", [])

            # Learnings section
            learnings = summary.get("learnings", {})

            # Build message
            lines = [
                "🌅 *Skill Auto-Improver Morning Brief*",
                "",
                f"📊 *Run ID:* `{run_id}`",
                f"⏰ *Period:* {period.title()}",
                "",
                "✅ *Improvements*",
                f"  • Skills improved: {skills_improved}/{total_trials}",
            ]

            # Add trial details if available
            trial_details = improvements.get("trial_details", [])
            if trial_details:
                for trial in trial_details:
                    skill = trial.get("skill", "unknown")
                    proposals = trial.get("proposals", 0)
                    score = trial.get("evaluation_score", "N/A")
                    lines.append(
                        f"    - {skill}: {proposals} proposals, score={score}"
                    )

            # Blocks section
            if failed_skills or errors:
                lines.append("")
                lines.append("⚠️  *Blocks*")
                if failed_skills:
                    lines.append(f"  • Failed skills: {', '.join(failed_skills)}")
                if errors:
                    for error in errors[:3]:  # Limit to 3 errors
                        lines.append(f"    - {error[:100]}")
            else:
                lines.append("")
                lines.append("🎯 *No blocking issues*")

            # Learnings section
            lines.append("")
            lines.append("🧠 *Shared Brain Learning*")
            lines.append(
                f"  • Promotion wisdom entries: {learnings.get('promotion_wisdom_count', 0)}"
            )
            lines.append(
                f"  • Regression patterns: {learnings.get('regression_patterns_count', 0)}"
            )
            lines.append(f"  • Fixture library size: {learnings.get('fixture_library_size', 0)}")
            lines.append(
                f"  • Skill mastery records: {learnings.get('skill_mastery_entries', 0)}"
            )

            lines.append("")
            lines.append("📝 *Next Steps:* Review run history in skill-auto-improver/runs/")

            return "\n".join(lines)
        except Exception as e:
            self.logger.error(f"Failed to format message: {e}", exc_info=True)
            return f"Failed to format morning summary: {e}"

    def send_telegram_message(self, message: str) -> bool:
        """
        Send formatted message via Telegram.

        Args:
            message: Formatted message string

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if not self.telegram_token or not self.telegram_chat_id:
                self.logger.warning(
                    "Telegram credentials not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)"
                )
                self.logger.info("Message preview:")
                self.logger.info(message)
                return False

            # Import requests here to avoid hard dependency
            try:
                import requests
            except ImportError:
                self.logger.warning("requests library not available; cannot send Telegram message")
                self.logger.info("Message preview:")
                self.logger.info(message)
                return False

            # Send via Telegram Bot API
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            self.logger.info(f"Telegram message sent successfully (status={response.status_code})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}", exc_info=True)
            return False

    def archive_summary(self, summary: Dict[str, Any]) -> None:
        """
        Archive sent summary with timestamp.

        Args:
            summary: Dict with summary data
        """
        try:
            now = datetime.utcnow()
            archive_filename = f"{now.strftime('%Y-%m-%d')}-summary.json"
            archive_path = self.archive_dir / archive_filename

            # If file exists, append to array instead
            if archive_path.exists():
                with open(archive_path, "r") as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    existing.append(summary)
                else:
                    existing = [existing, summary]
            else:
                existing = [summary]

            with open(archive_path, "w") as f:
                json.dump(existing, f, indent=2)

            self.logger.info(f"Summary archived to {archive_path}")
        except Exception as e:
            self.logger.error(f"Failed to archive summary: {e}", exc_info=True)

    def run(self) -> bool:
        """
        Execute full morning summary sender workflow.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("=" * 80)
        self.logger.info("MORNING SUMMARY SENDER STARTING")
        self.logger.info("=" * 80)

        try:
            # 1. Load summary
            summary = self.load_summary()
            if not summary:
                self.logger.warning("No summary available; exiting")
                return False

            # 2. Format message
            message = self.format_message(summary)

            # 3. Send via Telegram
            send_success = self.send_telegram_message(message)

            # 4. Archive summary regardless of send success
            self.archive_summary(summary)

            # 5. Final log
            self.logger.info("=" * 80)
            self.logger.info("MORNING SUMMARY SENDER COMPLETE")
            self.logger.info("=" * 80)

            return True

        except Exception as e:
            self.logger.error(f"Morning summary sender failed: {e}", exc_info=True)
            return False


def main():
    """Entry point for morning summary sender cron job."""
    workspace_root = os.getenv("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace"))

    sender = MorningSummarySender(workspace_root)
    success = sender.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
