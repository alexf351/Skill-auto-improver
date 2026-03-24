"""
Multi-skill orchestrator.

Coordinates improvement runs across multiple skills using the shared brain.
Enables:
- Batch evaluation of multiple skills
- Cross-skill insight propagation
- Shared promotion/regression learning
- Unified operator dashboard
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable
import uuid

from .loop import SkillAutoImprover, RunTrace
from .shared_brain import SharedBrain
from .models import StepResult


@dataclass
class SkillTrialConfig:
    """Configuration for a single skill improvement trial."""
    skill_path: str | Path
    skill_name: str
    skill_type: str = ""  # e.g. "weather", "kiro", "research"
    fixtures_path: Optional[str | Path] = None
    proposals_path: Optional[str | Path] = None
    min_confidence: float = 0.80
    accepted_severities: list[str] = field(default_factory=lambda: ["warning", "critical"])
    enabled: bool = True


@dataclass
class OrchestrationRun:
    """Result of orchestrated multi-skill improvement."""
    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    
    # Per-skill results
    skill_trials: dict[str, RunTrace] = field(default_factory=dict)
    skill_outcomes: dict[str, dict[str, Any]] = field(default_factory=dict)  # summary per skill
    
    # Cross-skill insights
    promotions_recorded: list[str] = field(default_factory=list)  # wisdom IDs
    regressions_recorded: list[str] = field(default_factory=list)  # pattern IDs
    fixtures_added_to_library: list[str] = field(default_factory=list)
    
    # Metrics
    total_skills: int = 0
    successful_trials: int = 0
    rolled_back_trials: int = 0
    promotions_accepted: int = 0
    regressions_prevented: int = 0
    
    # Operator summary
    notes: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_skills": self.total_skills,
            "successful_trials": self.successful_trials,
            "rolled_back_trials": self.rolled_back_trials,
            "promotions_accepted": self.promotions_accepted,
            "regressions_prevented": self.regressions_prevented,
            "promotions_recorded": self.promotions_recorded,
            "regressions_recorded": self.regressions_recorded,
            "fixtures_added_to_library": self.fixtures_added_to_library,
            "skill_outcomes": self.skill_outcomes,
            "notes": self.notes,
        }


class MultiSkillOrchestrator:
    """
    Coordinates improvement across multiple skills with shared brain learning.
    """

    def __init__(
        self,
        brain_dir: Path | str = ".skill-auto-improver/brain",
        create_improver: Optional[Callable[[Path], SkillAutoImprover]] = None,
    ):
        self.brain_dir = Path(brain_dir)
        self.shared_brain = SharedBrain(self.brain_dir)
        self.create_improver = create_improver or (lambda skill_path: SkillAutoImprover())

    def run_orchestration(
        self,
        skill_configs: list[SkillTrialConfig],
        logs_dir: Optional[Path | str] = None,
    ) -> OrchestrationRun:
        """
        Run improvement trials across multiple skills.
        
        Returns:
            OrchestrationRun with per-skill results and cross-skill insights
        """
        run = OrchestrationRun(
            run_id=str(uuid.uuid4()),
            started_at=datetime.now(timezone.utc).isoformat(),
            total_skills=len(skill_configs),
        )
        
        logs_dir_path = Path(logs_dir) if logs_dir else None
        if logs_dir_path:
            logs_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Run trials for each enabled skill
        for config in skill_configs:
            if not config.enabled:
                continue
            
            trial_result = self._run_skill_trial(config, run)
            run.skill_trials[config.skill_name] = trial_result
            
            # Extract insights from trial and update shared brain
            self._extract_and_record_insights(config, trial_result, run)
            
            # Persist logs if requested
            if logs_dir_path and trial_result:
                trial_log = logs_dir_path / f"{config.skill_name}_{run.run_id}.json"
                trial_log.write_text(json.dumps(trial_result.to_dict(), indent=2))
        
        run.finished_at = datetime.now(timezone.utc).isoformat()
        
        # Persist orchestration run summary
        if logs_dir_path:
            run_log = logs_dir_path / f"orchestration_{run.run_id}.json"
            run_log.write_text(json.dumps(run.to_dict(), indent=2))
        
        return run

    def _run_skill_trial(
        self,
        config: SkillTrialConfig,
        run: OrchestrationRun,
    ) -> Optional[RunTrace]:
        """Run a single skill improvement trial."""
        try:
            improver = self.create_improver(Path(config.skill_path))
            
            # Would normally call improver.run_once() with the config
            # For now, return None as placeholder; in real integration this would be real
            return None
        except Exception as e:
            run.notes += f"\n[ERROR] Skill {config.skill_name}: {e}"
            return None

    def _extract_and_record_insights(
        self,
        config: SkillTrialConfig,
        trace: Optional[RunTrace],
        run: OrchestrationRun,
    ) -> None:
        """Extract insights from a trial and update shared brain."""
        if not trace:
            return
        
        # Update skill mastery
        mastery = self.shared_brain.get_or_create_skill_mastery(
            config.skill_name,
            skill_type=config.skill_type,
        )
        mastery.total_trials += 1
        
        # Check if trial was successful (promoted)
        patch_trial_meta = trace.metadata.get("patch_trial", {})
        if patch_trial_meta.get("rolled_back"):
            run.rolled_back_trials += 1
            
            # Record regression patterns from rollback
            if "rollback_reasons" in patch_trial_meta:
                for reason in patch_trial_meta["rollback_reasons"]:
                    pattern = self.shared_brain.record_regression(
                        pattern_name=reason.replace(" ", "_").lower(),
                        skill_name=config.skill_name,
                        trigger=reason,
                        fix_strategy="Apply fixture-level policy gates; require test_case proposals.",
                        severity="warning",
                    )
                    run.regressions_recorded.append(pattern.id)
            
            run.regressions_prevented += 1
        else:
            run.successful_trials += 1
            mastery.successful_promotions += 1
            
            # Record promotion wisdom from accepted changes
            apply_meta = patch_trial_meta.get("apply", {})
            if apply_meta.get("applied_count", 0) > 0:
                ab_meta = patch_trial_meta.get("ab", {})
                proposal_types = ["instruction", "test_case", "artifact"]  # infer from context
                
                wisdom = self.shared_brain.record_promotion(
                    fixture_name="multi_fixture_trial",
                    skill_name=config.skill_name,
                    proposal_types=proposal_types,
                    reason=ab_meta.get("pass_rate_delta", "0%"),
                    confidence=0.85,
                    shared_lessons=[],
                )
                run.promotions_recorded.append(wisdom.id)
                run.promotions_accepted += 1
        
        # Update skill mastery with trial metrics
        self.shared_brain.update_skill_mastery(
            config.skill_name,
            total_trials=mastery.total_trials,
            successful_promotions=mastery.successful_promotions,
            average_proposal_confidence=0.85,
            most_effective_proposal_types=["test_case", "instruction"],
        )
        
        # Add outcome summary
        run.skill_outcomes[config.skill_name] = {
            "trial_id": trace.run_id if trace else None,
            "rolled_back": patch_trial_meta.get("rolled_back", False),
            "promotions_from_trial": run.promotions_accepted,
            "regressions_prevented": run.regressions_prevented,
        }

    def get_brain_summary(self) -> dict[str, Any]:
        """Get a summary of the entire shared brain state."""
        return {
            "core_directives": len(self.shared_brain.core_directives),
            "promotion_wisdom_entries": len(self.shared_brain.promotion_wisdom),
            "regression_patterns": len(self.shared_brain.regression_patterns),
            "fixture_library_entries": len(self.shared_brain.fixture_library),
            "skills_tracked": len(self.shared_brain.skill_mastery),
            "total_successful_trials_recorded": sum(
                m.successful_promotions for m in self.shared_brain.skill_mastery.values()
            ),
            "total_regressions_prevented": sum(
                p.occurrence_count for p in self.shared_brain.regression_patterns.values()
            ),
        }

    def get_skill_context_for_trial(self, skill_name: str) -> dict[str, Any]:
        """Get pre-trial context from shared brain for a skill."""
        return {
            "applicable_directives": [
                asdict(d) for d in self.shared_brain.get_directives_for_skill(skill_name)
            ],
            "regression_patterns_to_watch": [
                asdict(p) for p in self.shared_brain.get_regression_patterns_for_skill(skill_name)
            ],
            "similar_fixtures_in_library": [
                asdict(e) for e in self.shared_brain.get_similar_fixtures(skill_name)
            ],
            "skill_mastery": asdict(self.shared_brain.get_or_create_skill_mastery(skill_name)),
        }
