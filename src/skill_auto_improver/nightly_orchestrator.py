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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import MultiSkillOrchestrator, SkillTrialConfig, OrchestrationRun
from shared_brain import SharedBrain
from logger import SkillAutoImproverLogger


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

        # Logger
        self.logger = SkillAutoImproverLogger(name="nightly-orchestrator")

        # Initialize orchestrator with shared brain
        self.brain = SharedBrain(str(self.brain_root))
        self.orchestrator = MultiSkillOrchestrator(self.brain)

        # Target skills to monitor
        self.target_skills = [
            "morning-brief",
            "weather-brief",
            "kiro-dev-assistant",
            "kiro-content-calendar",
            "kiro-ugc-brief",
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
                self.logger.info(f"Discovered skill: {skill_name} at {skill_path}")
            else:
                self.logger.warning(f"Skill not found: {skill_name} at {skill_path}")
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
                min_confidence=0.70,
                max_proposals=10,
                run_evaluations=True,
                use_shared_brain=True,
            )
            configs.append(config)
            self.logger.info(f"Created trial config for {skill_name}")
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
            self.logger.info(
                f"Starting nightly orchestration trial for {len(configs)} skills at {datetime.utcnow().isoformat()}"
            )

            # Execute orchestration
            run_result = self.orchestrator.run_orchestration(configs)

            self.logger.info(f"Orchestration trial completed: {run_result.run_id}")
            self.logger.info(f"  - Skills attempted: {run_result.skills_attempted}")
            self.logger.info(f"  - Skills successful: {run_result.skills_successful}")
            self.logger.info(f"  - Total trials: {len(run_result.trial_results)}")

            return run_result
        except Exception as e:
            self.logger.error(f"Orchestration trial failed: {e}", exc_info=True)
            return None

    def log_run_to_history(self, run_result: OrchestrationRun) -> None:
        """
        Append orchestration run to run-history.jsonl.

        Args:
            run_result: OrchestrationRun object
        """
        try:
            # Convert run result to dict
            run_dict = {
                "timestamp": datetime.utcnow().isoformat(),
                "run_id": run_result.run_id,
                "skills_attempted": run_result.skills_attempted,
                "skills_successful": run_result.skills_successful,
                "total_trials": len(run_result.trial_results),
                "trial_results": [
                    {
                        "skill_name": tr.skill_name,
                        "status": tr.status,
                        "proposals_count": len(tr.proposals) if tr.proposals else 0,
                        "evaluation_score": tr.evaluation_score,
                        "metrics": tr.metrics,
                    }
                    for tr in run_result.trial_results
                ],
            }

            # Append to jsonl
            with open(self.run_history_path, "a") as f:
                f.write(json.dumps(run_dict) + "\n")

            self.logger.info(f"Logged run to {self.run_history_path}")
        except Exception as e:
            self.logger.error(f"Failed to log run to history: {e}", exc_info=True)

    def prepare_morning_summary(self, run_result: OrchestrationRun) -> Dict[str, Any]:
        """
        Prepare morning summary with learnings, blocks, and improvements.

        Args:
            run_result: OrchestrationRun object

        Returns:
            Dict with morning summary data
        """
        try:
            # Get brain summary
            brain_summary = self.brain.summarize()

            # Build summary structure
            morning_summary = {
                "timestamp": datetime.utcnow().isoformat(),
                "period": "nightly",
                "run_id": run_result.run_id,
                "improvements": {
                    "skills_improved": run_result.skills_successful,
                    "total_trials": len(run_result.trial_results),
                    "trial_details": [
                        {
                            "skill": tr.skill_name,
                            "proposals": len(tr.proposals) if tr.proposals else 0,
                            "evaluation_score": tr.evaluation_score,
                        }
                        for tr in run_result.trial_results
                        if tr.status == "success"
                    ],
                },
                "blocks": {
                    "failed_skills": [
                        tr.skill_name for tr in run_result.trial_results if tr.status != "success"
                    ],
                    "error_messages": [
                        tr.error_message for tr in run_result.trial_results if tr.error_message
                    ],
                },
                "learnings": {
                    "promotion_wisdom_count": len(brain_summary.get("promotion_wisdom", [])),
                    "regression_patterns_count": len(brain_summary.get("regression_patterns", [])),
                    "fixture_library_size": len(brain_summary.get("fixture_library", [])),
                    "skill_mastery_entries": len(brain_summary.get("skill_mastery", {})),
                },
                "brain_state": brain_summary,
            }

            # Save to file for morning-summary cron to pick up
            with open(self.morning_summary_path, "w") as f:
                json.dump(morning_summary, f, indent=2)

            self.logger.info(f"Morning summary prepared and saved to {self.morning_summary_path}")
            return morning_summary
        except Exception as e:
            self.logger.error(f"Failed to prepare morning summary: {e}", exc_info=True)
            return {}

    def run(self) -> bool:
        """
        Execute full nightly orchestration workflow.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("=" * 80)
        self.logger.info("NIGHTLY ORCHESTRATOR STARTING")
        self.logger.info("=" * 80)

        try:
            # 1. Discover installed skills
            discovered = self.discover_installed_skills()
            if not discovered:
                self.logger.warning("No target skills found; exiting")
                return False

            # 2. Create trial configs
            configs = self.create_trial_configs(discovered)

            # 3. Run orchestration
            run_result = self.run_orchestration_trial(configs)
            if not run_result:
                self.logger.error("Orchestration trial failed; exiting")
                return False

            # 4. Log to history
            self.log_run_to_history(run_result)

            # 5. Prepare morning summary
            morning_summary = self.prepare_morning_summary(run_result)

            # 6. Final log
            self.logger.info("=" * 80)
            self.logger.info("NIGHTLY ORCHESTRATOR COMPLETE")
            self.logger.info(f"Morning summary available at: {self.morning_summary_path}")
            self.logger.info("=" * 80)

            return True

        except Exception as e:
            self.logger.error(f"Nightly orchestrator failed: {e}", exc_info=True)
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
