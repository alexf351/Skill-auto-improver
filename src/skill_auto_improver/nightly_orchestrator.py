"""
Nightly Orchestrator Cron Job

Runs at 2 AM PST every night to:
1. Execute multi-skill improvement trials across all monitored skills
2. Log results to run-history.jsonl
3. Prepare morning summary with learnings, blocks, and improvements
4. Signal morning-summary cron to send Telegram notification

Triggered by: OpenClaw cron scheduler at 02:00 PST daily
Dependencies: orchestrator.py, shared_brain.py, logger.py
Output: run-history.jsonl, morning-summary.json
"""

import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from .orchestrator import MultiSkillOrchestrator, SkillTrialConfig, OrchestrationRun
from .shared_brain import SharedBrain
from .logger import TraceLogger

# Simple logger
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("nightly-orchestrator")


class NightlyOrchestratorRunner:
    """Orchestrates nightly skill improvement trials and result logging."""

    def __init__(self, workspace_root: str, run_history_path: Optional[str] = None):
        """
        Initialize nightly orchestrator.

        Args:
            workspace_root: Root path of OpenClaw workspace (typically ~/.openclaw/workspace)
            run_history_path: Path to run-history.jsonl (defaults to workspace/skill-auto-improver/runs/)
        """
        self.workspace_root = Path(workspace_root)
        self.skill_auto_improver_root = self.workspace_root / "skill-auto-improver"
        self.skills_root = self.workspace_root / "skills"

        # Setup paths
        if run_history_path:
            self.run_history_path = Path(run_history_path)
        else:
            self.run_history_path = self.skill_auto_improver_root / "runs" / "run-history.jsonl"

        self.run_history_path.parent.mkdir(parents=True, exist_ok=True)

        # Paths for shared brain and morning summary
        self.brain_root = self.skill_auto_improver_root / "shared_brain"
        self.morning_summary_path = self.skill_auto_improver_root / "runs" / "morning-summary.json"

        # Initialize orchestrator with shared brain
        self.orchestrator = MultiSkillOrchestrator(str(self.brain_root))
        self.brain = SharedBrain(str(self.brain_root))

        # Target skills to monitor
        self.target_skills = [
            "morning-brief",
            "weather-brief",
            "kiro-dev-assistant",
            "kiro-content-calendar",
            "kiro-ugc-brief",
            "kiro-shortform-engine",
        ]

    def discover_installed_skills(self) -> Dict[str, Path]:
        """
        Discover installed skills matching target names.

        Returns:
            Dict mapping skill names to their paths (empty if not found)
        """
        discovered = {}
        for skill_name in self.target_skills:
            skill_path = self.skills_root / skill_name
            if skill_path.exists() and (skill_path / "SKILL.md").exists():
                discovered[skill_name] = skill_path
                logger.info(f"Discovered skill: {skill_name} at {skill_path}")
            else:
                logger.warning(f"Skill not found: {skill_name} at {skill_path}")
        return discovered

    def create_trial_configs(self, discovered_skills: Dict[str, Path]) -> List[SkillTrialConfig]:
        """
        Create trial configurations for each discovered skill.

        Args:
            discovered_skills: Dict of skill_name -> Path

        Returns:
            List of SkillTrialConfig objects
        """
        configs = []
        for skill_name, skill_path in discovered_skills.items():
            config = SkillTrialConfig(
                skill_name=skill_name,
                skill_path=str(skill_path),
                skill_type=skill_name,
                min_confidence=0.70,
                accepted_severities=["warning", "critical"],
                enabled=True,
            )
            configs.append(config)
            logger.info(f"Created trial config for {skill_name}")
        return configs

    def run_orchestration_trial(self, configs: List[SkillTrialConfig]) -> Optional[OrchestrationRun]:
        """
        Execute orchestration trial across all skills.

        Args:
            configs: List of SkillTrialConfig objects

        Returns:
            OrchestrationRun result or None if error
        """
        try:
            logger.info(
                f"Starting nightly orchestration trial for {len(configs)} skills at {datetime.utcnow().isoformat()}"
            )

            # Execute orchestration
            run_result = self.orchestrator.run_orchestration(configs)

            logger.info(f"Orchestration trial completed: {run_result.run_id}")
            logger.info(f"  - Total skills: {run_result.total_skills}")
            logger.info(f"  - Successful trials: {run_result.successful_trials}")
            logger.info(f"  - Rolled back trials: {run_result.rolled_back_trials}")

            return run_result
        except Exception as e:
            logger.error(f"Orchestration trial failed: {e}", exc_info=True)
            return None

    def log_run_to_history(self, run_result: OrchestrationRun) -> None:
        """
        Append orchestration run to run-history.jsonl.

        Args:
            run_result: OrchestrationRun object
        """
        try:
            # Convert run result to dict
            run_dict = run_result.to_dict()
            run_dict["timestamp"] = datetime.utcnow().isoformat()

            # Append to jsonl
            with open(self.run_history_path, "a") as f:
                f.write(json.dumps(run_dict) + "\n")

            logger.info(f"Logged run to {self.run_history_path}")
        except Exception as e:
            logger.error(f"Failed to log run to history: {e}", exc_info=True)

    def prepare_morning_summary(self, run_result: OrchestrationRun) -> Dict[str, Any]:
        """
        Prepare morning summary with learnings, blocks, and improvements.

        Args:
            run_result: OrchestrationRun object

        Returns:
            Dict with morning summary data
        """
        try:
            raw_brain_summary = self.orchestrator.get_brain_summary()
            brain_summary = {
                "promotion_wisdom_count": raw_brain_summary.get("promotion_wisdom_entries", 0),
                "regression_patterns_count": raw_brain_summary.get("regression_patterns", 0),
                "fixture_library_size": raw_brain_summary.get("fixture_library_entries", 0),
                "skill_mastery_entries": raw_brain_summary.get("skills_tracked", 0),
                "total_successful_trials_recorded": raw_brain_summary.get("total_successful_trials_recorded", 0),
                "total_regressions_prevented": raw_brain_summary.get("total_regressions_prevented", 0),
            }

            # Build summary structure based on run results
            skill_trial_details = []
            for skill_name, trial in run_result.skill_trials.items():
                if trial:
                    proposals = []
                    for step in trial.steps:
                        if step.name in {"rank", "amend"}:
                            proposals = step.output.get("proposals", []) or proposals
                    skill_trial_details.append({
                        "skill": skill_name,
                        "status": getattr(trial, "status", "unknown"),
                        "proposals": len(proposals),
                    })
            
            morning_summary = {
                "timestamp": datetime.utcnow().isoformat(),
                "period": "nightly",
                "run_id": run_result.run_id,
                "improvements": {
                    "successful_trials": run_result.successful_trials,
                    "total_skills": run_result.total_skills,
                    "trial_details": skill_trial_details,
                },
                "blocks": {
                    "rolled_back_trials": run_result.rolled_back_trials,
                    "skill_outcomes": run_result.skill_outcomes,
                },
                "learnings": {
                    "promotions_recorded": len(run_result.promotions_recorded),
                    "regressions_recorded": len(run_result.regressions_recorded),
                    "fixtures_added": len(run_result.fixtures_added_to_library),
                    "promotions_accepted": run_result.promotions_accepted,
                    "regressions_prevented": run_result.regressions_prevented,
                },
                "brain_state": brain_summary,
            }

            # Save to file for morning-summary cron to pick up
            with open(self.morning_summary_path, "w") as f:
                json.dump(morning_summary, f, indent=2)

            logger.info(f"Morning summary prepared and saved to {self.morning_summary_path}")
            return morning_summary
        except Exception as e:
            logger.error(f"Failed to prepare morning summary: {e}", exc_info=True)
            return {}

    def run(self) -> bool:
        """
        Execute full nightly orchestration workflow.

        Returns:
            True if successful, False otherwise
        """
        logger.info("=" * 80)
        logger.info("NIGHTLY ORCHESTRATOR STARTING")
        logger.info("=" * 80)

        try:
            # 1. Discover installed skills
            discovered = self.discover_installed_skills()
            if not discovered:
                logger.warning("No target skills found; exiting")
                return False

            # 2. Create trial configs
            configs = self.create_trial_configs(discovered)

            # 3. Run orchestration
            run_result = self.run_orchestration_trial(configs)
            if not run_result:
                logger.error("Orchestration trial failed; exiting")
                return False

            # 4. Log to history
            self.log_run_to_history(run_result)

            # 5. Prepare morning summary
            morning_summary = self.prepare_morning_summary(run_result)

            # 6. Final log
            logger.info("=" * 80)
            logger.info("NIGHTLY ORCHESTRATOR COMPLETE")
            logger.info(f"Morning summary available at: {self.morning_summary_path}")
            logger.info("=" * 80)

            return True

        except Exception as e:
            logger.error(f"Nightly orchestrator failed: {e}", exc_info=True)
            return False


def main():
    """Entry point for nightly orchestrator cron job."""
    # Get workspace root from environment or use default
    workspace_root = os.getenv("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace"))

    runner = NightlyOrchestratorRunner(workspace_root)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
