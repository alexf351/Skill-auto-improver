from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Any
import os

from .logger import TraceLogger, load_traces, summarize_traces
from .models import RunTrace, StepResult
from .evaluator import GoldenEvaluator, GoldenFixture, EvaluationReport, TestResult
from .proposer import ProposalEngine, PatchProposal
from .ab_evaluator import ABEvaluator
from .applier import SkillPatchApplier
from .operating_memory import OperatingMemory
from .checklist_evaluator import ChecklistSpec, ChecklistEvaluator, ChecklistResult
from .memory_ranking import MemoryDrivenRanker
from .trial_workspace import TrialWorkspaceCompiler


def _build_change_guard(apply_output: dict[str, Any], policy: dict[str, Any], fixture_policies: dict[str, Any]) -> dict[str, Any]:
    applied = apply_output.get("applied", [])
    changed_targets = sorted({change.get("target_path", "") for change in applied if change.get("target_path")})
    total_added_lines = sum(((change.get("diff_summary") or {}).get("added_lines", 0) for change in applied))
    changed_fixture_names = {
        change.get("fixture_name")
        for change in applied
        if change.get("fixture_name")
    }
    effective_max_changed_targets = policy.get("max_changed_targets")
    effective_max_added_lines = policy.get("max_added_lines")

    constrained_fixtures: dict[str, dict[str, Any]] = {}
    for fixture_name, fixture_policy in fixture_policies.items():
        if not isinstance(fixture_policy, dict) or fixture_name not in changed_fixture_names:
            continue
        constrained_fixtures[fixture_name] = {
            "max_changed_targets": fixture_policy.get("max_changed_targets"),
            "max_added_lines": fixture_policy.get("max_added_lines"),
        }
        fixture_max_targets = fixture_policy.get("max_changed_targets")
        fixture_max_added = fixture_policy.get("max_added_lines")
        if fixture_max_targets not in (None, ""):
            if effective_max_changed_targets in (None, ""):
                effective_max_changed_targets = fixture_max_targets
            else:
                effective_max_changed_targets = min(int(effective_max_changed_targets), int(fixture_max_targets))
        if fixture_max_added not in (None, ""):
            if effective_max_added_lines in (None, ""):
                effective_max_added_lines = fixture_max_added
            else:
                effective_max_added_lines = min(int(effective_max_added_lines), int(fixture_max_added))

    exceeded: list[str] = []
    if effective_max_changed_targets not in (None, "") and len(changed_targets) > int(effective_max_changed_targets):
        exceeded.append(f"changed target count {len(changed_targets)} exceeds limit {int(effective_max_changed_targets)}")
    if effective_max_added_lines not in (None, "") and total_added_lines > int(effective_max_added_lines):
        exceeded.append(f"added line count {total_added_lines} exceeds limit {int(effective_max_added_lines)}")

    return {
        "changed_targets": changed_targets,
        "changed_target_count": len(changed_targets),
        "total_added_lines": total_added_lines,
        "max_changed_targets": None if effective_max_changed_targets in (None, "") else int(effective_max_changed_targets),
        "max_added_lines": None if effective_max_added_lines in (None, "") else int(effective_max_added_lines),
        "fixture_constraints": constrained_fixtures,
        "exceeded": exceeded,
        "is_safe": len(exceeded) == 0,
    }


class Stage(Protocol):
    def __call__(self, context: dict) -> dict: ...


def _dict_to_evaluation_report(d: dict[str, Any]) -> EvaluationReport:
    results = []
    for r_dict in d.get("results", []):
        test_result = TestResult(
            fixture_name=r_dict.get("fixture_name", ""),
            passed=r_dict.get("passed", False),
            expected=r_dict.get("expected", {}),
            actual=r_dict.get("actual", {}),
            delta=r_dict.get("delta", {}),
            reason=r_dict.get("reason", ""),
        )
        results.append(test_result)

    return EvaluationReport(
        total=d.get("total", 0),
        passed=d.get("passed", 0),
        failed=d.get("failed", 0),
        results=results,
    )


def _proposal_source(context: dict[str, Any]) -> dict[str, Any]:
    ranked_output = context.get("rank")
    if isinstance(ranked_output, dict) and "proposals" in ranked_output:
        return ranked_output
    amend_output = context.get("amend")
    if isinstance(amend_output, dict):
        return amend_output
    return {}


def _update_trace_metadata(trace: RunTrace, step_name: str, output: dict[str, Any]) -> None:
    if step_name == "evaluate" and {"total", "passed", "failed"}.issubset(output.keys()):
        trace.metadata["evaluation"] = {
            "mode": "golden",
            "total": output.get("total", 0),
            "passed": output.get("passed", 0),
            "failed": output.get("failed", 0),
            "pass_rate": output.get("pass_rate", 0.0),
        }
    elif step_name == "evaluate" and {"checklist_name", "total_outputs", "total_passed"}.issubset(output.keys()):
        trace.metadata["evaluation"] = {
            "mode": "checklist",
            "checklist_name": output.get("checklist_name", ""),
            "total_outputs": output.get("total_outputs", 0),
            "total_passed": output.get("total_passed", 0),
            "pass_rate": output.get("pass_rate", 0.0),
            "average_score": output.get("average_score", 0.0),
        }
    elif step_name == "evaluate" and output.get("mode") in {"fixture_only", "checklist_only", "hybrid_either_or", "hybrid_both_required"}:
        fixture_eval = output.get("fixture_evaluation", {})
        checklist_eval = output.get("checklist_evaluation", {})
        trace.metadata["evaluation"] = {
            "mode": output.get("mode"),
            "passed": output.get("passed", False),
            "fixture_pass_rate": fixture_eval.get("pass_rate"),
            "checklist_pass_rate": checklist_eval.get("pass_rate"),
            "checklist_average_score": checklist_eval.get("average_score"),
        }

    if {"accepted", "rolled_back", "ab", "apply"}.issubset(output.keys()):
        ab_output = output.get("ab", {})
        apply_output = output.get("apply", {})
        applied_changes = apply_output.get("applied", [])
        trace.metadata["patch_trial"] = {
            "accepted": output.get("accepted", False),
            "rolled_back": output.get("rolled_back", False),
            "rollback_count": output.get("rollback_count", 0),
            "applied_count": apply_output.get("applied_count", 0),
            "skipped_count": apply_output.get("skipped_count", 0),
            "pass_rate_delta": ab_output.get("pass_rate_delta", 0.0),
            "recovered_count": ab_output.get("recovered_count", 0),
            "regressed_count": ab_output.get("regressed_count", 0),
            "is_safe": ab_output.get("is_safe", False),
            "acceptance_reason": output.get("acceptance_reason", ""),
            "backup_ids": [change.get("backup_id") for change in applied_changes if change.get("backup_id")],
            "diff_summaries": [
                {
                    "target_path": change.get("target_path", ""),
                    "added_lines": (change.get("diff_summary") or {}).get("added_lines", 0),
                    "removed_lines": (change.get("diff_summary") or {}).get("removed_lines", 0),
                    "preview": (change.get("diff_summary") or {}).get("preview", []),
                }
                for change in applied_changes
                if change.get("diff_summary")
            ],
            "operating_memory": output.get("operating_memory", {}).get("context"),
            "promotion_guard": output.get("promotion_guard"),
            "change_guard": output.get("change_guard"),
            "promotion": output.get("operating_memory", {}).get("promotion"),
            "backup_summary": output.get("backup_summary"),
        }


@dataclass(slots=True)
class SkillAutoImprover:
    observe: Stage
    inspect: Stage
    amend: Stage
    evaluate: Stage
    workspace: Stage | None = None
    rank: Stage | None = None
    stage_order: list[str] | None = None

    def run_once(self, skill_path: str | Path, logs_dir: str | Path = "./runs") -> RunTrace:
        trace = RunTrace(skill_path=str(skill_path))
        context: dict = {"skill_path": str(skill_path), "trace_id": trace.run_id}

        default_order = ["observe", "amend"]
        if self.workspace:
            default_order.append("workspace")
        default_order.extend(["inspect"])
        if self.rank:
            default_order.append("rank")
        default_order.append("evaluate")

        order = self.stage_order or default_order
        stages = {
            "observe": self.observe,
            "inspect": self.inspect,
            "amend": self.amend,
            "evaluate": self.evaluate,
        }
        if self.workspace:
            stages["workspace"] = self.workspace
        if self.rank:
            stages["rank"] = self.rank

        for name in order:
            if name not in stages:
                continue
            stage = stages[name]
            step = StepResult(name=name, output={})
            try:
                output = stage(context)
                if output is None:
                    output = {}
                step.output = output
                context[name] = output
                _update_trace_metadata(trace, name, output)
                step.finish()
                trace.add_step(step)
            except Exception as exc:  # pragma: no cover
                step.output = {"error": str(exc)}
                step.finish()
                trace.add_step(step)
                trace.complete(status="error")
                TraceLogger(logs_dir).write(trace)
                return trace

        trace.complete(status="ok")
        TraceLogger(logs_dir).write(trace)
        return trace


def create_recent_run_observer_stage(
    logs_dir: str | Path,
    *,
    limit: int = 10,
) -> Stage:
    def observe(context: dict) -> dict:
        skill_path = context.get("skill_path")
        traces = load_traces(logs_dir, limit=limit)
        summary = summarize_traces(traces, skill_path=skill_path)
        signals: list[str] = []
        if summary["trace_count"] == 0:
            signals.append("no recent trace history")
        if summary["total_regressions"] > 0:
            signals.append(f"recent regressions detected: {summary['total_regressions']}")
        if summary["acceptance_reasons"].get("no proposals applied"):
            signals.append("recent runs had blocked or unsupported proposals")
        if summary["acceptance_reasons"].get("promoted baseline regression"):
            signals.append("promoted baseline protection was triggered recently")
        if summary["acceptance_reasons"].get("promotion history regression"):
            signals.append("promotion-history protection was triggered recently")
        if summary["total_recoveries"] > 0:
            signals.append(f"recent recoveries landed: {summary['total_recoveries']}")
        hottest_regressed = (summary.get("fixture_hotspots") or {}).get("regressed", [])
        if hottest_regressed:
            top = hottest_regressed[0]
            signals.append(f"fixture hotspot: {top['fixture_name']} regressed {top['count']}x recently")
        summary["signals"] = signals
        summary["logs_dir"] = str(logs_dir)
        return summary

    return observe


def create_trial_workspace_stage(
    *,
    fixtures: list[GoldenFixture] | None = None,
    policy: dict[str, Any] | None = None,
    logs_dir: str | Path | None = None,
) -> Stage:
    def build_workspace(context: dict) -> dict:
        skill_path = context.get("skill_path")
        if not skill_path:
            return {"error": "Missing skill_path in context"}

        proposal_source = _proposal_source(context)
        compiler = TrialWorkspaceCompiler(skill_path, logs_dir=logs_dir)
        report = compiler.compile(
            fixtures=fixtures,
            proposals=proposal_source.get("proposals", []),
            policy=policy or context.get("policy") or {},
        )
        return report.to_dict()

    return build_workspace


def create_trace_inspect_stage() -> Stage:
    def inspect(context: dict) -> dict:
        observe_output = context.get("observe", {})
        acceptance_reasons = observe_output.get("acceptance_reasons", {})
        priorities: list[str] = []
        hypotheses: list[str] = []

        if acceptance_reasons.get("promoted baseline regression"):
            priorities.append("protect promoted fixtures before attempting broader amendments")
            hypotheses.append("recent proposals touched already-working behavior and need narrower targeting")
        if acceptance_reasons.get("promotion history regression"):
            priorities.append("compare against multiple promoted states before accepting broader skill edits")
            hypotheses.append("the latest baseline passed, but historically stable fixtures are being re-broken")
        if acceptance_reasons.get("regression detected"):
            priorities.append("prefer smallest reversible changes with explicit regression-fixture coverage")
            hypotheses.append("patches are overreaching and should add test-case proposals alongside instruction edits")

        hottest_regressed = (observe_output.get("fixture_hotspots") or {}).get("regressed", [])
        if hottest_regressed:
            top = hottest_regressed[0]
            priorities.append(f"focus the next amendment on hotspot fixture '{top['fixture_name']}' before broad edits")
            hypotheses.append(f"fixture '{top['fixture_name']}' is absorbing repeated regressions and likely needs narrower, fixture-specific coverage")
        if acceptance_reasons.get("no proposals applied"):
            priorities.append("improve proposal applicability or operator-policy alignment")
            hypotheses.append("good proposals are being filtered out by type/confidence/severity gates")

        workspace = context.get("workspace", {})
        for warning in workspace.get("warnings", []):
            if warning == "fixtures exist but no proposals supplied":
                priorities.append("generate or source candidate proposals for the known failing fixtures")
                hypotheses.append("the current loop has evaluation context but lacks amendment inputs")
            elif warning == "proposals exist without fixture context":
                priorities.append("restore fixture-backed verification before mutating the skill")
                hypotheses.append("proposal generation has become detached from measurable success criteria")
            elif warning == "all proposals currently sit below the active confidence floor":
                priorities.append("either raise proposal quality or relax policy gates intentionally")
                hypotheses.append("useful changes are being blocked by confidence thresholds rather than regression safety")
        if observe_output.get("trace_count", 0) == 0:
            priorities.append("establish baseline trial data before optimizing policy")
            hypotheses.append("there is not enough run history yet to bias proposal strategy")
        if not priorities:
            priorities.append("continue iterating on the highest-confidence failing fixture")
            hypotheses.append("recent history does not show a dominant failure mode")

        return {
            "priorities": priorities,
            "hypotheses": hypotheses,
            "recent_failure_count": len(observe_output.get("latest_failures", [])),
            "recent_success_count": len(observe_output.get("latest_successes", [])),
            "acceptance_reasons": acceptance_reasons,
            "fixture_hotspots": observe_output.get("fixture_hotspots", {}),
        }

    return inspect


def create_golden_evaluator_stage(
    fixtures: list[GoldenFixture],
) -> Stage:
    def evaluate(context: dict) -> dict:
        evaluator = GoldenEvaluator(fixtures)
        actual_outputs = context.get("actual_outputs", {})
        if not actual_outputs:
            amend_output = context.get("amend", {})
            if amend_output:
                actual_outputs = {fixtures[0].name: amend_output} if fixtures else {}

        report = evaluator.evaluate_all(actual_outputs)
        return report.to_dict()

    return evaluate


def create_amendment_proposal_stage(
    golden_evaluator: GoldenEvaluator | None = None,
) -> Stage:
    def amend(context: dict) -> dict:
        engine = ProposalEngine()
        eval_output = context.get("evaluate", {})
        if not eval_output.get("results") and golden_evaluator is not None:
            actual_outputs = context.get("actual_outputs", {})
            if actual_outputs:
                eval_output = golden_evaluator.evaluate_all(actual_outputs).to_dict()

        eval_results = eval_output.get("results", [])

        skill_path = context.get("skill_path")
        memory_context = None
        if skill_path:
            memory_context = OperatingMemory(skill_path).load_context()

        failed_results = []
        for result_dict in eval_results:
            if not result_dict.get("passed", True):
                test_result = TestResult(
                    fixture_name=result_dict.get("fixture_name", ""),
                    passed=result_dict.get("passed", False),
                    expected=result_dict.get("expected", {}),
                    actual=result_dict.get("actual", {}),
                    delta=result_dict.get("delta", {}),
                    reason=result_dict.get("reason", ""),
                )
                failed_results.append(test_result)

        proposal_report = engine.generate_proposals(
            failed_results,
            operating_memory=memory_context,
            inspect_context=context.get("inspect"),
            skill_path=skill_path,
        )
        result = proposal_report.to_dict()
        if eval_output.get("results") and not context.get("evaluate"):
            result["evaluation_seed"] = eval_output
        return result

    return amend


def create_proposal_ranking_stage() -> Stage:
    """Reorder proposals using memory-driven fixture success history.
    
    Uses MemoryDrivenRanker to intelligently order proposals based on:
    - Which proposal types succeeded for each fixture before
    - Fixture difficulty (harder fixtures get safer proposals first)
    - Cross-fixture similarity (learn from similar fixtures)
    - Recency weighting (recent successes matter more)
    
    Proposals are reordered in-place in the output, preserving all metadata.
    Non-existent rank files are handled gracefully (no ranking applied).
    """
    def rank_proposals(context: dict) -> dict:
        skill_path = context.get("skill_path")
        amend_output = context.get("amend", {})
        proposal_dicts = amend_output.get("proposals", [])
        
        if not proposal_dicts or not skill_path:
            # No proposals to rank or no skill context
            return amend_output
        
        try:
            ranker = MemoryDrivenRanker(skill_path)
            
            # Group proposals by fixture for ranking
            proposals_by_fixture: dict[str, list[tuple[int, dict]]] = {}
            for idx, p_dict in enumerate(proposal_dicts):
                fixture_name = p_dict.get("fixture_name", "")
                if fixture_name not in proposals_by_fixture:
                    proposals_by_fixture[fixture_name] = []
                proposals_by_fixture[fixture_name].append((idx, p_dict))
            
            # Rank proposals for each fixture
            ranked_indices: dict[int, float] = {}  # original_index -> rank_score
            for fixture_name, fixture_proposals in proposals_by_fixture.items():
                # Convert dicts to PatchProposal objects for ranking
                proposal_objs = []
                dict_to_obj = {}  # Track mapping from object back to dict
                for _, p_dict in fixture_proposals:
                    obj = PatchProposal(
                        type=p_dict.get("type", ""),
                        description=p_dict.get("description", ""),
                        content=p_dict.get("content", {}),
                        fixture_name=p_dict.get("fixture_name", ""),
                        severity=p_dict.get("severity", "info"),
                        confidence=p_dict.get("confidence", 0.0),
                    )
                    proposal_objs.append(obj)
                    dict_to_obj[id(obj)] = p_dict
                
                # Rank the objects
                ranked = ranker.rank_proposals(proposal_objs, fixture_name)
                
                # Map rank scores back to original indices
                for ranked_obj, score in ranked:
                    original_dict = dict_to_obj.get(id(ranked_obj))
                    if original_dict:
                        for orig_idx, p_dict in fixture_proposals:
                            if p_dict is original_dict:
                                ranked_indices[orig_idx] = score
                                break
            
            # Reorder proposals by descending rank score
            # Proposals without a score (shouldn't happen) go to the end
            sorted_proposal_indices = sorted(
                range(len(proposal_dicts)),
                key=lambda i: ranked_indices.get(i, -1.0),
                reverse=True
            )
            
            reordered_proposals = [proposal_dicts[i] for i in sorted_proposal_indices]
            
            # Return updated context with reordered proposals
            result = dict(amend_output)
            result["proposals"] = reordered_proposals
            result["ranking_applied"] = True
            result["rank_scores"] = {i: ranked_indices.get(i, 0.0) for i in range(len(proposal_dicts))}
            return result
            
        except Exception as e:
            # Graceful degradation: if ranking fails, return original proposals
            result = dict(amend_output)
            result["ranking_applied"] = False
            result["ranking_error"] = str(e)
            return result
    
    return rank_proposals


def create_patch_apply_stage(
    *,
    accepted_types: set[str] | None = None,
    mode: str = "plan",
    min_confidence: float = 0.0,
    accepted_severities: set[str] | None = None,
) -> Stage:
    def apply_patches(context: dict) -> dict:
        skill_path = context.get("skill_path")
        proposal_source = _proposal_source(context)
        proposal_dicts = proposal_source.get("proposals", [])

        proposals = [
            PatchProposal(
                type=p.get("type", ""),
                description=p.get("description", ""),
                content=p.get("content", {}),
                fixture_name=p.get("fixture_name", ""),
                severity=p.get("severity", "info"),
                confidence=p.get("confidence", 0.0),
            )
            for p in proposal_dicts
        ]

        report = SkillPatchApplier(skill_path).apply(
            proposals,
            accepted_types=accepted_types,
            mode=mode,
            min_confidence=min_confidence,
            accepted_severities=accepted_severities,
            fixture_policies=(context.get("policy") or {}).get("fixture_policies"),
        )
        return report.to_dict()

    return apply_patches


def create_safe_patch_trial_stage(
    fixtures: list[GoldenFixture],
    evaluate_skill: callable,
    *,
    accepted_types: set[str] | None = None,
    rollback_on_regression: bool = True,
    min_confidence: float = 0.0,
    accepted_severities: set[str] | None = None,
    require_improvement: bool = True,
) -> Stage:
    def safe_trial(context: dict) -> dict:
        skill_path = context.get("skill_path")
        if not skill_path:
            return {"error": "Missing skill_path in context"}

        memory = OperatingMemory(skill_path)
        memory.ensure()
        memory_context = memory.load_context()
        merged_policy = memory.merge_policy(
            {
                "accepted_types": sorted(accepted_types) if accepted_types else None,
                "min_confidence": min_confidence,
                "accepted_severities": sorted(accepted_severities) if accepted_severities else None,
                "rollback_on_regression": rollback_on_regression,
                "require_recovery_for_accept": False,
            }
        )
        effective_rollback_on_regression = merged_policy.get("rollback_on_regression", rollback_on_regression)
        effective_min_confidence = float(merged_policy.get("min_confidence") or 0.0)
        severity_values = merged_policy.get("accepted_severities") or accepted_severities
        effective_accepted_severities = set(severity_values) if severity_values else None
        require_recovery_for_accept = bool(merged_policy.get("require_recovery_for_accept", False)) or require_improvement
        protect_promoted_fixtures = bool(merged_policy.get("protect_promoted_fixtures", True))
        rollback_on_history_regression = bool(merged_policy.get("rollback_on_history_regression", True))
        require_test_case_for_protected = bool(merged_policy.get("require_test_case_for_protected_fixtures", False))

        evaluator = GoldenEvaluator(fixtures)
        applier = SkillPatchApplier(skill_path)

        before_dict = context.get("before_eval")
        if before_dict:
            before_report = _dict_to_evaluation_report(before_dict)
        else:
            before_outputs = evaluate_skill(skill_path, context, "before")
            before_report = evaluator.evaluate_all(before_outputs)
            before_dict = before_report.to_dict()

        proposal_source = _proposal_source(context)
        proposal_dicts = proposal_source.get("proposals", [])
        proposals = [
            PatchProposal(
                type=p.get("type", ""),
                description=p.get("description", ""),
                content=p.get("content", {}),
                fixture_name=p.get("fixture_name", ""),
                severity=p.get("severity", "info"),
                confidence=p.get("confidence", 0.0),
            )
            for p in proposal_dicts
        ]

        fixture_policies = dict(merged_policy.get("fixture_policies") or {})
        if require_test_case_for_protected:
            promotion_profiles = (memory_context.get("proposal_hints") or {}).get("promotion_profiles", {})
            for fixture_name, profile in promotion_profiles.items():
                if not profile.get("historically_protected"):
                    continue
                existing = dict(fixture_policies.get(fixture_name) or {})
                required = set(existing.get("required_proposal_types") or [])
                required.update(profile.get("required_proposal_types") or ["test_case"])
                existing["required_proposal_types"] = sorted(required)
                fixture_policies[fixture_name] = existing

        apply_report = applier.apply(
            proposals,
            accepted_types=accepted_types,
            mode="apply",
            min_confidence=effective_min_confidence,
            accepted_severities=effective_accepted_severities,
            fixture_policies=fixture_policies,
        )
        change_guard = _build_change_guard(apply_report.to_dict(), merged_policy, fixture_policies)

        after_outputs = evaluate_skill(skill_path, context, "after")
        after_report = evaluator.evaluate_all(after_outputs)
        ab_report = ABEvaluator().compare(before_report, after_report)
        promotion_guard = memory.evaluate_promotion_guard(
            before_eval=before_dict,
            after_eval=after_report.to_dict(),
            history_window=int(merged_policy.get("promotion_history_window") or 0) or None,
            min_promotions_for_fixture_guard=int(merged_policy.get("min_promotions_for_fixture_guard") or 2),
        )

        acceptance_reason = "safe improvement"
        accepted = ab_report.is_safe
        if apply_report.applied_count == 0:
            accepted = False
            acceptance_reason = "no proposals applied"
        elif require_recovery_for_accept and ab_report.recovered_count <= 0:
            accepted = False
            acceptance_reason = "no recovered failures"
        elif ab_report.pass_rate_delta <= 0:
            accepted = False
            acceptance_reason = "no measurable improvement"
        elif not change_guard.get("is_safe", True):
            accepted = False
            acceptance_reason = "change budget exceeded"
        elif protect_promoted_fixtures and promotion_guard.get("regressed_from_promoted"):
            accepted = False
            acceptance_reason = "promoted baseline regression"
        elif protect_promoted_fixtures and promotion_guard.get("regressed_from_promotion_history"):
            accepted = False
            acceptance_reason = "promotion history regression"

        rollback_reports: list[dict[str, Any]] = []
        rolled_back = False
        should_rollback = False
        if apply_report.applied_count > 0:
            if protect_promoted_fixtures and promotion_guard.get("regressed_from_promoted"):
                should_rollback = True
                acceptance_reason = "promoted baseline regression"
            elif protect_promoted_fixtures and rollback_on_history_regression and promotion_guard.get("regressed_from_promotion_history"):
                should_rollback = True
                acceptance_reason = "promotion history regression"
            elif effective_rollback_on_regression and not ab_report.is_safe:
                should_rollback = True
                acceptance_reason = "regression detected"
            elif not change_guard.get("is_safe", True):
                should_rollback = True
                acceptance_reason = "change budget exceeded"
            elif not accepted:
                should_rollback = True
        if should_rollback:
            for change in reversed(apply_report.applied):
                if change.backup_path:
                    restore = applier.restore_backup(change.backup_path)
                    rollback_reports.append(restore.to_dict())
                    continue
                target_path = change.target_path
                if target_path and os.path.exists(target_path):
                    Path(target_path).unlink()
                    rollback_reports.append({
                        "skill_path": str(skill_path),
                        "backup_path": "",
                        "target_path": target_path,
                        "restored": True,
                        "detail": "removed newly created file during rollback",
                    })
            rolled_back = any(r.get("restored") for r in rollback_reports)

        result = {
            "before_eval": before_dict,
            "apply": apply_report.to_dict(),
            "after_eval": after_report.to_dict(),
            "ab": ab_report.to_dict(),
            "accepted": accepted,
            "acceptance_reason": acceptance_reason,
            "rolled_back": rolled_back,
            "rollback_count": sum(1 for r in rollback_reports if r.get("restored")),
            "rollback_reports": rollback_reports,
            "policy": merged_policy,
            "promotion_guard": promotion_guard,
            "change_guard": change_guard,
            "backup_summary": memory.summarize_backups(),
        }

        memory_result = memory.record_trial(
            result=result,
            proposals=proposal_dicts,
            policy=merged_policy,
        )
        result["operating_memory"] = memory_result
        result["backup_summary"] = memory.summarize_backups()
        return result

    return safe_trial


def create_ab_evaluation_stage() -> Stage:
    def ab_evaluate(context: dict) -> dict:
        evaluator = ABEvaluator()
        before_dict = context.get("before_eval", {})
        after_dict = context.get("after_eval", {})

        if not before_dict or not after_dict:
            return {
                "error": "Missing before_eval or after_eval in context",
                "before_provided": bool(before_dict),
                "after_provided": bool(after_dict),
            }

        before_report = _dict_to_evaluation_report(before_dict)
        after_report = _dict_to_evaluation_report(after_dict)
        ab_report = evaluator.compare(before_report, after_report)
        return ab_report.to_dict()

    return ab_evaluate


def create_checklist_evaluator_stage(
    checklist: ChecklistSpec,
) -> Stage:
    """
    Evaluate outputs against a checklist of yes/no questions.
    Returns a checklist evaluation report with scores and pass/fail per output.
    """
    def evaluate(context: dict) -> dict:
        evaluator = ChecklistEvaluator(checklist)
        actual_outputs = context.get("actual_outputs", {})
        
        if not actual_outputs:
            amend_output = context.get("amend", {})
            if amend_output:
                actual_outputs = {"output": amend_output}
        
        report = evaluator.evaluate_all(actual_outputs)
        return report.to_dict()
    
    return evaluate


def create_checklist_with_custom_evaluator_stage(
    checklist: ChecklistSpec,
    evaluator_fn: callable,
) -> Stage:
    """
    Evaluate outputs using a custom evaluator function (e.g., LLM-based).
    The function should take (output: dict, question: ChecklistQuestion) -> bool.
    """
    def evaluate(context: dict) -> dict:
        evaluator = ChecklistEvaluator(checklist, evaluator_fn=evaluator_fn)
        actual_outputs = context.get("actual_outputs", {})
        
        if not actual_outputs:
            amend_output = context.get("amend", {})
            if amend_output:
                actual_outputs = {"output": amend_output}
        
        report = evaluator.evaluate_all(actual_outputs)
        return report.to_dict()
    
    return evaluate


def create_hybrid_evaluation_stage(
    fixtures: list[GoldenFixture] | None = None,
    checklist: ChecklistSpec | None = None,
    require_both: bool = False,
) -> Stage:
    """
    Hybrid evaluation that supports fixture mode, checklist mode, or both.
    
    Args:
        fixtures: Optional golden fixtures for fixture-based evaluation
        checklist: Optional checklist spec for checklist-based evaluation
        require_both: If True, both gates must pass. If False, either can pass.
    
    Returns:
        A stage that performs the appropriate evaluations and combines results.
    """
    def evaluate(context: dict) -> dict:
        result = {}
        actual_outputs = context.get("actual_outputs", {})
        
        if not actual_outputs:
            amend_output = context.get("amend", {})
            if amend_output:
                actual_outputs = {"output": amend_output}
        
        fixture_result = None
        checklist_result = None
        
        if fixtures:
            evaluator = GoldenEvaluator(fixtures)
            fixture_report = evaluator.evaluate_all(actual_outputs)
            fixture_result = fixture_report.to_dict()
            result["fixture_evaluation"] = fixture_result
        
        if checklist:
            evaluator = ChecklistEvaluator(checklist)
            checklist_report = evaluator.evaluate_all(actual_outputs)
            checklist_result = checklist_report.to_dict()
            result["checklist_evaluation"] = checklist_result
        
        if not fixtures and not checklist:
            return {"error": "No fixtures or checklist provided"}
        
        # Determine overall pass/fail based on mode
        if require_both and fixture_result and checklist_result:
            fixture_pass = fixture_result.get("passed", 0) == fixture_result.get("total", 0)
            checklist_pass = checklist_result.get("total_passed", 0) == checklist_result.get("total_outputs", 0)
            result["mode"] = "hybrid_both_required"
            result["passed"] = fixture_pass and checklist_pass
        elif fixture_result and checklist_result:
            # Either/or mode
            fixture_pass = fixture_result.get("passed", 0) == fixture_result.get("total", 0)
            checklist_pass = checklist_result.get("total_passed", 0) == checklist_result.get("total_outputs", 0)
            result["mode"] = "hybrid_either_or"
            result["passed"] = fixture_pass or checklist_pass
        elif fixture_result:
            result["mode"] = "fixture_only"
            result["passed"] = fixture_result.get("passed", 0) == fixture_result.get("total", 0)
        elif checklist_result:
            result["mode"] = "checklist_only"
            result["passed"] = checklist_result.get("total_passed", 0) == checklist_result.get("total_outputs", 0)
        
        return result
    
    return evaluate


def run_once(skill_path: str | Path, logs_dir: str | Path = "./runs") -> RunTrace:
    def noop(_: dict) -> dict:
        return {}

    return SkillAutoImprover(observe=noop, inspect=noop, amend=noop, evaluate=noop).run_once(
        skill_path=skill_path,
        logs_dir=logs_dir,
    )
