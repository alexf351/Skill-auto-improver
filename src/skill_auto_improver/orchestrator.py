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

import inspect
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable
import uuid

from .loop import SkillAutoImprover, RunTrace
from .models import StepResult
from .shared_brain import SharedBrain
from .logger import TraceLogger


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
    accepted_types: list[str] = field(default_factory=lambda: ["instruction", "test_case"])
    enabled: bool = True

    def __post_init__(self) -> None:
        self.skill_path = Path(self.skill_path)
        if self.fixtures_path is not None:
            self.fixtures_path = Path(self.fixtures_path)
        if self.proposals_path is not None:
            self.proposals_path = Path(self.proposals_path)
        self.validate()

    def validate(self) -> None:
        if not str(self.skill_name).strip():
            raise ValueError("skill_name must be a non-empty string")
        try:
            confidence = float(self.min_confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("min_confidence must be a number between 0.0 and 1.0") from exc
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")
        self.min_confidence = confidence

        if not isinstance(self.accepted_severities, list) or not self.accepted_severities:
            raise ValueError("accepted_severities must be a non-empty list of strings")
        normalized = []
        for severity in self.accepted_severities:
            if not isinstance(severity, str) or not severity.strip():
                raise ValueError("accepted_severities must contain only non-empty strings")
            normalized.append(severity.strip())
        self.accepted_severities = normalized

        if not isinstance(self.accepted_types, list) or not self.accepted_types:
            raise ValueError("accepted_types must be a non-empty list of strings")
        normalized_types = []
        for proposal_type in self.accepted_types:
            if not isinstance(proposal_type, str) or not proposal_type.strip():
                raise ValueError("accepted_types must contain only non-empty strings")
            normalized_types.append(proposal_type.strip())
        self.accepted_types = normalized_types

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillTrialConfig":
        if not isinstance(data, dict):
            raise ValueError("each orchestration config entry must be an object")
        return cls(**data)


@dataclass
class TrialPreflightIssue:
    """Review-friendly preflight validation issue for a skill trial."""
    code: str
    message: str
    path: Optional[str] = None
    level: str = "error"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "level": self.level,
        }
        if self.path:
            payload["path"] = self.path
        return payload


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

    @staticmethod
    def _normalized_patch_trial_metadata(patch_trial_meta: dict[str, Any]) -> dict[str, Any]:
        """Accept both flat loop metadata and nested stage-output metadata."""
        apply_meta = patch_trial_meta.get("apply") or {}
        ab_meta = patch_trial_meta.get("ab") or {}

        applied = apply_meta.get("applied", patch_trial_meta.get("applied", [])) or []
        skipped = apply_meta.get("skipped", patch_trial_meta.get("skipped", [])) or []

        return {
            "accepted": patch_trial_meta.get("accepted", False),
            "rolled_back": patch_trial_meta.get("rolled_back", False),
            "acceptance_reason": patch_trial_meta.get("acceptance_reason", ""),
            "apply": {
                "applied_count": apply_meta.get("applied_count", patch_trial_meta.get("applied_count", len(applied))),
                "skipped_count": apply_meta.get("skipped_count", patch_trial_meta.get("skipped_count", len(skipped))),
                "applied": applied,
                "skipped": skipped,
            },
            "ab": {
                "pass_rate_delta": ab_meta.get("pass_rate_delta", patch_trial_meta.get("pass_rate_delta", 0.0)),
                "recovered_count": ab_meta.get("recovered_count", patch_trial_meta.get("recovered_count", 0)),
                "regressed_count": ab_meta.get("regressed_count", patch_trial_meta.get("regressed_count", 0)),
                "is_safe": ab_meta.get("is_safe", patch_trial_meta.get("is_safe", True)),
            },
        }

    def __init__(
        self,
        brain_dir: Path | str = ".skill-auto-improver/brain",
        create_improver: Optional[Callable[[Path], SkillAutoImprover]] = None,
    ):
        self.brain_dir = Path(brain_dir)
        self.shared_brain = SharedBrain(self.brain_dir)
        self.create_improver = create_improver or self._create_default_improver

    @staticmethod
    def _create_default_improver(skill_path: Path) -> SkillAutoImprover:
        """Create a lightweight no-op improver so orchestration can always run.

        The nightly orchestrator should never crash just because no custom stage
        pipeline was injected. This default pipeline records an audited trace with
        a small amount of skill metadata, but makes no file changes.
        """

        def observe(_: dict[str, Any]) -> dict[str, Any]:
            skill_file = Path(skill_path) / "SKILL.md"
            if not skill_file.exists():
                raise FileNotFoundError(f"Missing SKILL.md for {skill_path}")
            text = skill_file.read_text()
            return {
                "skill_file": str(skill_file),
                "line_count": len(text.splitlines()),
                "char_count": len(text),
                "has_frontmatter": text.startswith("---"),
            }

        def inspect(context: dict[str, Any]) -> dict[str, Any]:
            observed = context.get("observe", {})
            findings: list[str] = []
            if not observed.get("has_frontmatter"):
                findings.append("missing frontmatter")
            if observed.get("line_count", 0) > 500:
                findings.append("skill may be too long for efficient loading")
            return {
                "findings": findings,
                "status": "review_needed" if findings else "healthy",
            }

        def amend(context: dict[str, Any]) -> dict[str, Any]:
            inspection = context.get("inspect", {})
            return {
                "proposals": [],
                "status": "no_changes_applied",
                "reason": "default nightly audit mode",
                "findings": inspection.get("findings", []),
            }

        def evaluate(context: dict[str, Any]) -> dict[str, Any]:
            inspection = context.get("inspect", {})
            passed = 0 if inspection.get("findings") else 1
            return {
                "total": 1,
                "passed": passed,
                "failed": 1 - passed,
                "pass_rate": float(passed),
                "results": [
                    {
                        "fixture_name": "skill_audit",
                        "passed": bool(passed),
                        "expected": {"status": "healthy"},
                        "actual": {"status": inspection.get("status", "unknown")},
                        "delta": {"findings": inspection.get("findings", [])},
                        "reason": "default nightly audit",
                    }
                ],
            }

        return SkillAutoImprover(observe=observe, inspect=inspect, amend=amend, evaluate=evaluate)

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

    def _create_improver_for_trial(
        self,
        skill_path: Path,
        config: SkillTrialConfig,
        brain_context: dict[str, Any],
    ) -> SkillAutoImprover:
        """Create an improver while remaining backward compatible with older factories."""
        factory = self.create_improver
        parameter_count = len(inspect.signature(factory).parameters)
        if parameter_count >= 3:
            return factory(skill_path, config, brain_context)
        if parameter_count == 2:
            return factory(skill_path, config)
        return factory(skill_path)

    def _load_fixture_names(self, fixtures_path: Optional[str | Path]) -> list[str]:
        if not fixtures_path:
            return []
        path = Path(fixtures_path)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text())
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        fixture_names: list[str] = []
        for item in payload:
            if isinstance(item, dict) and item.get("name"):
                fixture_names.append(str(item["name"]))
        return fixture_names

    def _build_trial_context(self, config: SkillTrialConfig) -> dict[str, Any]:
        fixture_names = self._load_fixture_names(config.fixtures_path)
        fixture_suggestions = {
            fixture_name: [
                item.to_dict()
                for item in self.shared_brain.suggest_fixture_templates(fixture_name, limit=3)
            ]
            for fixture_name in fixture_names
        }
        return {
            "config": {
                "skill_name": config.skill_name,
                "skill_type": config.skill_type,
                "fixtures_path": str(config.fixtures_path) if config.fixtures_path else None,
                "proposals_path": str(config.proposals_path) if config.proposals_path else None,
                "min_confidence": config.min_confidence,
                "accepted_severities": list(config.accepted_severities),
                "accepted_types": list(config.accepted_types),
                "enabled": config.enabled,
            },
            "brain": self.get_skill_context_for_trial(config.skill_name),
            "fixture_names": fixture_names,
            "fixture_suggestions": fixture_suggestions,
        }

    def _validate_json_payload(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc

    @staticmethod
    def _normalize_proposals_payload(payload: Any) -> list[Any]:
        if isinstance(payload, dict):
            payload = payload.get("proposals")
        if not isinstance(payload, list):
            raise ValueError("proposals payload must be a JSON list or an object with a 'proposals' list")
        return payload

    @staticmethod
    def _validate_proposal_fixture_links(fixtures_payload: list[Any], proposals_payload: list[Any]) -> list[str]:
        fixture_names = {
            str(item.get("name", "")).strip()
            for item in fixtures_payload
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
        issues: list[str] = []
        for index, item in enumerate(proposals_payload):
            if not isinstance(item, dict):
                continue
            fixture_name = str(item.get("fixture_name", "")).strip()
            if fixture_name and fixture_name not in fixture_names:
                issues.append(
                    f"index {index}: proposal fixture_name '{fixture_name}' does not match any fixture name in the fixtures file"
                )
        return issues

    @staticmethod
    def _proposal_coverage_issues(fixtures_payload: list[Any], proposals_payload: list[Any]) -> list[str]:
        fixture_names = [
            str(item.get("name", "")).strip()
            for item in fixtures_payload
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        targeted_fixture_names = {
            str(item.get("fixture_name", "")).strip()
            for item in proposals_payload
            if isinstance(item, dict) and str(item.get("fixture_name", "")).strip()
        }

        issues: list[str] = []
        uncovered_fixtures = [name for name in fixture_names if name not in targeted_fixture_names]
        if uncovered_fixtures:
            issues.append(
                "fixtures without matching proposals: " + ", ".join(sorted(uncovered_fixtures))
            )

        duplicate_targets: dict[tuple[str, str], list[int]] = {}
        duplicate_artifact_paths: dict[str, list[int]] = {}
        for index, item in enumerate(proposals_payload):
            if not isinstance(item, dict):
                continue
            fixture_name = str(item.get("fixture_name", "")).strip()
            proposal_type = str(item.get("type", "")).strip()
            if fixture_name and proposal_type:
                duplicate_targets.setdefault((fixture_name, proposal_type), []).append(index)

            if proposal_type != "artifact":
                continue
            content = item.get("content")
            if not isinstance(content, dict):
                continue
            target_path = str(content.get("target_path", "")).strip()
            if not target_path:
                continue
            normalized_target = str(Path(target_path))
            duplicate_artifact_paths.setdefault(normalized_target, []).append(index)

        for (fixture_name, proposal_type), indexes in sorted(duplicate_targets.items()):
            if len(indexes) < 2:
                continue
            index_list = ", ".join(str(index) for index in indexes)
            issues.append(
                f"duplicate proposal target cluster for fixture '{fixture_name}' and type '{proposal_type}' "
                f"across indexes [{index_list}]"
            )

        for target_path, indexes in sorted(duplicate_artifact_paths.items()):
            if len(indexes) < 2:
                continue
            index_list = ", ".join(str(index) for index in indexes)
            issues.append(
                f"artifact proposal target_path '{target_path}' conflicts across indexes [{index_list}] "
                "and makes apply order ambiguous"
            )

        return issues

    @staticmethod
    def _normalized_proposal_policy_view(item: dict[str, Any]) -> dict[str, Any]:
        proposal_type = str(item.get("type", "")).strip().lower()
        severity_raw = item.get("severity")
        severity = None
        if severity_raw is not None:
            severity = str(severity_raw).strip().lower()
        return {
            **item,
            "type": proposal_type,
            "severity": severity,
        }

    @staticmethod
    def _proposal_meets_policy(item: dict[str, Any], config: SkillTrialConfig) -> bool:
        normalized = MultiSkillOrchestrator._normalized_proposal_policy_view(item)
        accepted_types = {proposal_type.strip().lower() for proposal_type in config.accepted_types}
        accepted_severities = {severity.strip().lower() for severity in config.accepted_severities}

        proposal_type = normalized.get("type", "")
        if proposal_type and proposal_type not in accepted_types:
            return False

        confidence = normalized.get("confidence")
        if confidence is not None:
            try:
                if float(confidence) < float(config.min_confidence):
                    return False
            except (TypeError, ValueError):
                return False

        severity = normalized.get("severity")
        if severity is not None and severity not in accepted_severities:
            return False

        return True

    def _proposal_policy_issues(
        self,
        fixtures_payload: list[Any],
        proposals_payload: list[Any],
        config: SkillTrialConfig,
    ) -> list[str]:
        fixture_names = [
            str(item.get("name", "")).strip()
            for item in fixtures_payload
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        proposals_by_fixture: dict[str, list[dict[str, Any]]] = {name: [] for name in fixture_names}

        for item in proposals_payload:
            if not isinstance(item, dict):
                continue
            fixture_name = str(item.get("fixture_name", "")).strip()
            if fixture_name in proposals_by_fixture:
                proposals_by_fixture[fixture_name].append(item)

        issues: list[str] = []
        accepted_severities = ", ".join(config.accepted_severities)
        accepted_types = ", ".join(config.accepted_types)
        for fixture_name, fixture_proposals in proposals_by_fixture.items():
            if not fixture_proposals:
                continue
            if any(self._proposal_meets_policy(item, config) for item in fixture_proposals):
                continue

            proposal_summaries = []
            for item in fixture_proposals:
                normalized = self._normalized_proposal_policy_view(item)
                proposal_summaries.append(
                    f"{normalized.get('type') or 'unknown'}"
                    f"(confidence={item.get('confidence', 'missing')}, severity={normalized.get('severity', 'missing')})"
                )
            issues.append(
                f"fixture '{fixture_name}' has proposals but none meet policy "
                f"accepted_types=[{accepted_types}] / min_confidence={config.min_confidence:.2f} / "
                f"accepted_severities=[{accepted_severities}]: "
                + ", ".join(proposal_summaries)
            )

        return issues

    def _validate_fixture_entry(self, item: Any, index: int, skill_root: Path) -> list[str]:
        issues: list[str] = []
        if not isinstance(item, dict):
            return [f"index {index}: fixture must be an object"]
        if not str(item.get("name", "")).strip():
            issues.append(f"index {index}: fixture missing non-empty name")

        input_data = item.get("input_data")
        if not isinstance(input_data, dict):
            issues.append(f"index {index}: fixture input_data must be an object")
            return issues

        has_path = "path" in input_data
        has_command = "command" in input_data
        if has_path == has_command:
            issues.append(f"index {index}: fixture must declare exactly one of input_data.path or input_data.command")
        elif has_path and not isinstance(input_data.get("path"), str):
            issues.append(f"index {index}: input_data.path must be a string")
        elif has_command:
            command = input_data.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
                issues.append(f"index {index}: input_data.command must be a non-empty list of strings")

            cwd = input_data.get("cwd")
            if cwd is not None:
                if not isinstance(cwd, str) or not cwd.strip():
                    issues.append(f"index {index}: input_data.cwd must be a non-empty string when provided")
                else:
                    resolved_cwd = (skill_root / cwd).resolve()
                    try:
                        resolved_cwd.relative_to(skill_root.resolve())
                    except ValueError:
                        issues.append(f"index {index}: input_data.cwd must stay inside the skill root")

        expected_output = item.get("expected_output")
        if not isinstance(expected_output, dict):
            issues.append(f"index {index}: expected_output must be an object")

        return issues

    @staticmethod
    def _duplicate_fixture_name_issues(fixtures_payload: list[Any]) -> list[str]:
        seen: dict[str, int] = {}
        issues: list[str] = []
        for index, item in enumerate(fixtures_payload):
            if not isinstance(item, dict):
                continue
            fixture_name = str(item.get("name", "")).strip()
            if not fixture_name:
                continue
            if fixture_name in seen:
                issues.append(
                    f"index {index}: fixture name '{fixture_name}' duplicates index {seen[fixture_name]} and makes proposal targeting ambiguous"
                )
                continue
            seen[fixture_name] = index
        return issues

    @staticmethod
    def _artifact_target_issue(
        *,
        item: dict[str, Any],
        index: int,
        skill_root: Path,
    ) -> str | None:
        if str(item.get("type", "")).strip() != "artifact":
            return None

        content = item.get("content")
        if not isinstance(content, dict):
            return f"index {index}: artifact proposal content must be an object"

        target_path = content.get("target_path")
        if not isinstance(target_path, str) or not target_path.strip():
            return f"index {index}: artifact proposal target_path must be a non-empty string"

        resolved = (skill_root / target_path).resolve()
        try:
            resolved.relative_to(skill_root.resolve())
        except ValueError:
            return f"index {index}: artifact proposal target_path escapes the skill root"
        return None

    def _validate_proposal_entry(self, item: Any, index: int) -> list[str]:
        issues: list[str] = []
        if not isinstance(item, dict):
            return [f"index {index}: proposal must be an object"]
        if not str(item.get("type", "")).strip():
            issues.append(f"index {index}: proposal missing non-empty type")
        if not str(item.get("fixture_name", "")).strip():
            issues.append(f"index {index}: proposal missing non-empty fixture_name")

        confidence = item.get("confidence")
        if confidence is not None:
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                issues.append(f"index {index}: proposal confidence must be numeric when provided")
            else:
                if not 0.0 <= confidence_value <= 1.0:
                    issues.append(f"index {index}: proposal confidence must be between 0.0 and 1.0")

        severity = item.get("severity")
        if severity is not None and (not isinstance(severity, str) or not severity.strip()):
            issues.append(f"index {index}: proposal severity must be a non-empty string when provided")

        return issues

    def preflight_trial_config(self, config: SkillTrialConfig) -> list[TrialPreflightIssue]:
        """Validate that a trial config points at runnable local inputs before execution."""
        issues: list[TrialPreflightIssue] = []

        skill_path = Path(config.skill_path)
        if not skill_path.exists():
            issues.append(TrialPreflightIssue(
                code="missing_skill_path",
                message="skill path does not exist",
                path=str(skill_path),
            ))
            return issues

        if not skill_path.is_dir():
            issues.append(TrialPreflightIssue(
                code="invalid_skill_path",
                message="skill path must be a directory",
                path=str(skill_path),
            ))
        elif not (skill_path / "SKILL.md").exists():
            issues.append(TrialPreflightIssue(
                code="missing_skill_file",
                message="skill path is missing SKILL.md",
                path=str(skill_path / "SKILL.md"),
            ))

        fixtures_payload: list[Any] | None = None
        proposals_payload: list[Any] | None = None

        if config.fixtures_path:
            fixtures_path = Path(config.fixtures_path)
            if not fixtures_path.exists():
                issues.append(TrialPreflightIssue(
                    code="missing_fixtures",
                    message="fixtures file does not exist",
                    path=str(fixtures_path),
                ))
            else:
                try:
                    payload = self._validate_json_payload(fixtures_path)
                    if not isinstance(payload, list):
                        raise ValueError("fixtures payload must be a JSON list")
                    fixtures_payload = payload
                    entry_issues = [
                        problem
                        for index, item in enumerate(payload)
                        for problem in self._validate_fixture_entry(item, index, skill_path)
                    ]
                    entry_issues.extend(self._duplicate_fixture_name_issues(payload))
                    if entry_issues:
                        issues.append(TrialPreflightIssue(
                            code="invalid_fixtures_shape",
                            message="; ".join(entry_issues),
                            path=str(fixtures_path),
                        ))
                except ValueError as exc:
                    issues.append(TrialPreflightIssue(
                        code="invalid_fixtures_json",
                        message=str(exc),
                        path=str(fixtures_path),
                    ))

        if config.proposals_path:
            proposals_path = Path(config.proposals_path)
            if not proposals_path.exists():
                issues.append(TrialPreflightIssue(
                    code="missing_proposals",
                    message="proposals file does not exist",
                    path=str(proposals_path),
                ))
            else:
                try:
                    payload = self._validate_json_payload(proposals_path)
                    proposals_payload = self._normalize_proposals_payload(payload)
                    entry_issues = [
                        problem
                        for index, item in enumerate(proposals_payload)
                        for problem in self._validate_proposal_entry(item, index)
                    ]
                    entry_issues.extend(
                        issue
                        for index, item in enumerate(proposals_payload)
                        if isinstance(item, dict)
                        for issue in [self._artifact_target_issue(item=item, index=index, skill_root=skill_path)]
                        if issue
                    )
                    if entry_issues:
                        issues.append(TrialPreflightIssue(
                            code="invalid_proposals_shape",
                            message="; ".join(entry_issues),
                            path=str(proposals_path),
                        ))
                except ValueError as exc:
                    issues.append(TrialPreflightIssue(
                        code="invalid_proposals_json",
                        message=str(exc),
                        path=str(proposals_path),
                    ))

        if fixtures_payload is not None and proposals_payload is not None:
            link_issues = self._validate_proposal_fixture_links(fixtures_payload, proposals_payload)
            if link_issues:
                issues.append(TrialPreflightIssue(
                    code="proposal_fixture_mismatch",
                    message="; ".join(link_issues),
                    path=str(config.proposals_path),
                ))

            coverage_issues = self._proposal_coverage_issues(fixtures_payload, proposals_payload)
            if coverage_issues:
                issues.append(TrialPreflightIssue(
                    code="proposal_coverage_gap",
                    message="; ".join(coverage_issues),
                    path=str(config.proposals_path),
                ))

            policy_issues = self._proposal_policy_issues(fixtures_payload, proposals_payload, config)
            if policy_issues:
                issues.append(TrialPreflightIssue(
                    code="proposal_policy_gap",
                    message="; ".join(policy_issues),
                    path=str(config.proposals_path),
                ))

        return issues

    def _run_skill_trial(
        self,
        config: SkillTrialConfig,
        run: OrchestrationRun,
    ) -> Optional[RunTrace]:
        """Run a single skill improvement trial."""
        try:
            skill_path = Path(config.skill_path)
            brain_context = self._build_trial_context(config)
            preflight_issues = self.preflight_trial_config(config)
            skill_logs_dir = self.brain_dir.parent / "runs"

            if preflight_issues:
                trace = RunTrace(skill_path=str(skill_path))
                trace.metadata.setdefault("orchestration", brain_context)
                trace.metadata["orchestration"]["preflight"] = {
                    "ok": False,
                    "issue_count": len(preflight_issues),
                    "issues": [issue.to_dict() for issue in preflight_issues],
                }
                preflight_step = StepResult(
                    name="preflight",
                    output=trace.metadata["orchestration"]["preflight"],
                )
                preflight_step.finish()
                trace.add_step(preflight_step)
                trace.complete(status="error")
                TraceLogger(skill_logs_dir).write(trace)
                run.notes += (
                    f"\n[ERROR] Skill {config.skill_name}: preflight failed - "
                    + "; ".join(issue.message for issue in preflight_issues)
                )
                return trace

            improver = self._create_improver_for_trial(skill_path, config, brain_context)
            trace = improver.run_once(skill_path=skill_path, logs_dir=skill_logs_dir)
            trace.metadata.setdefault("orchestration", brain_context)
            trace.metadata["orchestration"]["preflight"] = {"ok": True, "issue_count": 0, "issues": []}

            if trace.status != "ok":
                run.notes += f"\n[ERROR] Skill {config.skill_name}: trial trace finished with status={trace.status}"

            if "patch_trial" in trace.metadata:
                trace.metadata["patch_trial"] = self._normalized_patch_trial_metadata(trace.metadata["patch_trial"])

            if not any(step.name == "patch_trial" for step in trace.steps):
                trace.metadata.setdefault("patch_trial", {
                    "accepted": False,
                    "rolled_back": False,
                    "acceptance_reason": "audit only - no proposals applied",
                    "apply": {"applied_count": 0, "skipped_count": 0, "applied": [], "skipped": []},
                    "ab": {"pass_rate_delta": 0.0, "recovered_count": 0, "regressed_count": 0, "is_safe": True},
                })
                synthetic_step = StepResult(
                    name="patch_trial",
                    output=trace.metadata["patch_trial"],
                )
                synthetic_step.finish()
                trace.add_step(synthetic_step)

            TraceLogger(skill_logs_dir).write(trace)
            return trace
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

        preflight = trace.metadata.get("orchestration", {}).get("preflight", {})
        if trace.status != "ok":
            self.shared_brain.update_skill_mastery(
                config.skill_name,
                total_trials=mastery.total_trials,
                successful_promotions=mastery.successful_promotions,
                regression_incidents=mastery.regression_incidents,
                average_proposal_confidence=mastery.average_proposal_confidence,
                most_effective_proposal_types=mastery.most_effective_proposal_types,
            )
            run.skill_outcomes[config.skill_name] = {
                "trial_id": trace.run_id,
                "status": trace.status,
                "preflight_ok": preflight.get("ok", True),
                "preflight_issues": preflight.get("issues", []),
                "accepted": False,
                "rolled_back": False,
                "applied_count": 0,
                "skipped_count": 0,
                "proposal_types": [],
                "promotions_from_trial": 0,
                "regressions_from_trial": 0,
            }
            return
        
        # Check if trial was successful (promoted)
        patch_trial_meta = self._normalized_patch_trial_metadata(trace.metadata.get("patch_trial", {}))
        apply_meta = patch_trial_meta.get("apply", {})
        ab_meta = patch_trial_meta.get("ab", {})
        applied_changes = apply_meta.get("applied", []) or []
        skipped_changes = apply_meta.get("skipped", []) or []
        proposal_types = sorted({
            change.get("proposal_type")
            for change in [*applied_changes, *skipped_changes]
            if isinstance(change, dict) and change.get("proposal_type")
        })
        average_confidence = float(config.min_confidence) if proposal_types else mastery.average_proposal_confidence

        regressions_from_trial = 0
        promotions_from_trial = 0
        if patch_trial_meta.get("rolled_back"):
            run.rolled_back_trials += 1
            regressions_from_trial = int(ab_meta.get("regressed_count", 0) or 0)

            regression_reasons = []
            if patch_trial_meta.get("acceptance_reason"):
                regression_reasons.append(str(patch_trial_meta["acceptance_reason"]))
            regression_reasons.extend(str(reason) for reason in patch_trial_meta.get("rollback_reasons", []) or [])
            for reason in dict.fromkeys(regression_reasons):
                pattern = self.shared_brain.record_regression(
                    pattern_name=reason.replace(" ", "_").lower(),
                    skill_name=config.skill_name,
                    trigger=reason,
                    fix_strategy="Apply fixture-level policy gates; require test_case proposals.",
                    severity="critical" if "regression" in reason else "warning",
                )
                run.regressions_recorded.append(pattern.id)

            if regressions_from_trial > 0:
                run.regressions_prevented += regressions_from_trial
        else:
            run.successful_trials += 1
            if patch_trial_meta.get("accepted"):
                mastery.successful_promotions += 1

            # Record promotion wisdom from accepted changes
            if patch_trial_meta.get("accepted") and apply_meta.get("applied_count", 0) > 0:
                promotions_from_trial = int(ab_meta.get("recovered_count", 0) or 0) or 1
                reason = (
                    f"accepted with pass_rate_delta={ab_meta.get('pass_rate_delta', 0.0)}; "
                    f"recovered={ab_meta.get('recovered_count', 0)}; regressed={ab_meta.get('regressed_count', 0)}"
                )
                wisdom = self.shared_brain.record_promotion(
                    fixture_name="multi_fixture_trial",
                    skill_name=config.skill_name,
                    proposal_types=proposal_types or ["instruction"],
                    reason=reason,
                    confidence=max(config.min_confidence, 0.85),
                    shared_lessons=[],
                )
                run.promotions_recorded.append(wisdom.id)
                run.promotions_accepted += 1

        # Update skill mastery with trial metrics
        self.shared_brain.update_skill_mastery(
            config.skill_name,
            total_trials=mastery.total_trials,
            successful_promotions=mastery.successful_promotions,
            regression_incidents=mastery.regression_incidents + regressions_from_trial,
            average_proposal_confidence=average_confidence,
            most_effective_proposal_types=proposal_types or ["test_case", "instruction"],
        )

        # Add outcome summary
        run.skill_outcomes[config.skill_name] = {
            "trial_id": trace.run_id if trace else None,
            "status": trace.status,
            "preflight_ok": preflight.get("ok", True),
            "preflight_issues": preflight.get("issues", []),
            "accepted": patch_trial_meta.get("accepted", False),
            "rolled_back": patch_trial_meta.get("rolled_back", False),
            "acceptance_reason": patch_trial_meta.get("acceptance_reason", ""),
            "applied_count": apply_meta.get("applied_count", 0),
            "skipped_count": apply_meta.get("skipped_count", 0),
            "proposal_types": proposal_types,
            "promotions_from_trial": promotions_from_trial,
            "regressions_from_trial": regressions_from_trial,
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
