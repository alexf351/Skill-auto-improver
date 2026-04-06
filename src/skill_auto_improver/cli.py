from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .evaluator import GoldenFixture, GoldenEvaluator
from .loop import create_safe_patch_trial_stage, _update_trace_metadata, create_hybrid_evaluation_stage
from .operating_memory import scaffold_operating_memory, OperatingMemory
from .applier import SkillPatchApplier
from .models import RunTrace, StepResult
from .logger import TraceLogger
from .checklist_evaluator import ChecklistLoader, ChecklistEvaluator
from .shared_brain import SharedBrain
from .orchestrator import MultiSkillOrchestrator, SkillTrialConfig
from .trial_workspace import TrialWorkspaceCompiler, render_trial_workspace_markdown


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_fixtures(path: str | Path) -> list[GoldenFixture]:
    raw = _load_json(path)
    return [GoldenFixture(**item) for item in raw]


def load_proposals(path: str | Path) -> list[dict[str, Any]]:
    raw = _load_json(path)
    if isinstance(raw, dict) and "proposals" in raw:
        return raw["proposals"]
    if isinstance(raw, list):
        return raw
    raise ValueError("proposals file must be a list or an object with a 'proposals' key")


def evaluate_file_contains_skill(skill_path: str, fixtures: list[GoldenFixture]) -> dict[str, dict[str, Any]]:
    skill_root = Path(skill_path)
    outputs: dict[str, dict[str, Any]] = {}

    for fixture in fixtures:
        probe = fixture.input_data or {}
        relative_path = probe.get("path")
        expected_contains = fixture.expected_output.get("contains", [])
        expected_not_contains = fixture.expected_output.get("not_contains", [])
        if not relative_path:
            raise ValueError(f"fixture '{fixture.name}' is missing input_data.path")

        target_path = skill_root / relative_path
        content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        matched = [snippet for snippet in expected_contains if snippet in content]
        still_absent = [snippet for snippet in expected_not_contains if snippet not in content]
        outputs[fixture.name] = {
            "contains": matched,
            "not_contains": still_absent,
        }

    return outputs


def _resolve_probe_cwd(skill_root: Path, probe: dict[str, Any], fixture_name: str) -> Path:
    cwd_value = probe.get("cwd", ".")
    if not isinstance(cwd_value, str) or not cwd_value.strip():
        raise ValueError(f"fixture '{fixture_name}' input_data.cwd must be a non-empty string when provided")

    resolved = (skill_root / cwd_value).resolve()
    try:
        resolved.relative_to(skill_root.resolve())
    except ValueError as exc:
        raise ValueError(f"fixture '{fixture_name}' input_data.cwd must stay inside the skill path") from exc
    return resolved


def evaluate_command_skill(skill_path: str, fixtures: list[GoldenFixture]) -> dict[str, dict[str, Any]]:
    skill_root = Path(skill_path)
    outputs: dict[str, dict[str, Any]] = {}

    for fixture in fixtures:
        probe = fixture.input_data or {}
        command = probe.get("command")
        if not command:
            raise ValueError(f"fixture '{fixture.name}' is missing input_data.command")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValueError(f"fixture '{fixture.name}' input_data.command must be a list of strings")

        command_cwd = _resolve_probe_cwd(skill_root, probe, fixture.name)
        timeout = probe.get("timeout_seconds", 10)
        completed = subprocess.run(
            command,
            cwd=command_cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

        expected = fixture.expected_output or {}
        stdout = completed.stdout
        stderr = completed.stderr
        outputs[fixture.name] = {
            "exit_code": completed.returncode,
            "stdout_contains": [snippet for snippet in expected.get("stdout_contains", []) if snippet in stdout],
            "stdout_not_contains": [snippet for snippet in expected.get("stdout_not_contains", []) if snippet not in stdout],
            "stderr_contains": [snippet for snippet in expected.get("stderr_contains", []) if snippet in stderr],
            "stderr_not_contains": [snippet for snippet in expected.get("stderr_not_contains", []) if snippet not in stderr],
        }

    return outputs


def evaluate_skill_fixtures(skill_path: str, fixtures: list[GoldenFixture]) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for fixture in fixtures:
        probe = fixture.input_data or {}
        if "path" in probe:
            outputs.update(evaluate_file_contains_skill(skill_path, [fixture]))
            continue
        if "command" in probe:
            outputs.update(evaluate_command_skill(skill_path, [fixture]))
            continue
        raise ValueError(f"fixture '{fixture.name}' must declare input_data.path or input_data.command")
    return outputs


def _read_jsonl_tail(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows[-limit:]


def _load_orchestration_configs(path: str | Path) -> list[SkillTrialConfig]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise ValueError("orchestration config file must be a list")

    configs: list[SkillTrialConfig] = []
    for index, item in enumerate(raw):
        try:
            configs.append(SkillTrialConfig.from_dict(item))
        except Exception as exc:
            raise ValueError(f"invalid orchestration config entry at index {index}: {exc}") from exc
    return configs


def _write_trace(
    *,
    skill_path: str,
    logs_dir: str | Path,
    command: str,
    cli_metadata: dict[str, Any],
    steps: list[tuple[str, dict[str, Any]]],
    status: str = "ok",
) -> str:
    trace = RunTrace(skill_path=str(skill_path))
    trace.metadata["cli"] = {
        "command": command,
        **cli_metadata,
    }

    for name, output in steps:
        step = StepResult(name=name, output=output)
        step.finish()
        trace.add_step(step)
        _update_trace_metadata(trace, name, output)

    trace.complete(status=status)
    return str(TraceLogger(logs_dir).write(trace))


def _write_trial_trace(
    *,
    skill_path: str,
    logs_dir: str | Path,
    fixtures_path: str,
    proposals_path: str,
    result: dict[str, Any],
) -> str:
    return _write_trace(
        skill_path=skill_path,
        logs_dir=logs_dir,
        command="trial",
        cli_metadata={
            "fixtures_path": str(fixtures_path),
            "proposals_path": str(proposals_path),
        },
        steps=[
            ("before_eval", result.get("before_eval", {})),
            ("apply_trial", result),
            ("after_eval", result.get("after_eval", {})),
        ],
        status="ok" if "error" not in result else "error",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-auto-improver",
        description="Run concrete safe patch trials against a skill folder.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    trial = subparsers.add_parser(
        "trial",
        help="Apply proposals to a skill, evaluate before/after, and auto-rollback regressions.",
    )
    trial.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    trial.add_argument("--fixtures", required=True, help="Path to golden fixture JSON file")
    trial.add_argument("--proposals", required=True, help="Path to proposal JSON file")
    trial.add_argument(
        "--accepted-types",
        nargs="+",
        default=["instruction", "test_case"],
        help="Proposal types allowed to apply during the trial",
    )
    trial.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum proposal confidence required before auto-apply",
    )
    trial.add_argument(
        "--accepted-severities",
        nargs="+",
        default=["info", "warning", "critical"],
        help="Proposal severities allowed to apply during the trial",
    )
    trial.add_argument(
        "--allow-no-improvement",
        action="store_true",
        help="Do not require a positive recovery/improvement delta before keeping a patch",
    )
    trial.add_argument(
        "--logs-dir",
        default=None,
        help="Optional directory to persist a structured trial trace JSON",
    )

    scaffold = subparsers.add_parser(
        "scaffold-memory",
        help="Scaffold the persistent operating-memory layer for a target skill.",
    )
    scaffold.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    scaffold.add_argument("--force", action="store_true", help="Overwrite existing memory files")

    backups = subparsers.add_parser(
        "inspect-backups",
        help="List backup snapshots with current diff previews for operator review.",
    )
    backups.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    backups.add_argument("--limit", type=int, default=None, help="Optional max number of backups to inspect")
    backups.add_argument("--target-name", default=None, help="Optional filename filter, e.g. SKILL.md")

    restore = subparsers.add_parser(
        "restore-backup",
        help="Restore a backup by full path or backup id (created_at token).",
    )
    restore.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    restore.add_argument("--backup", required=True, help="Backup path or backup id to restore")
    restore.add_argument("--target-name", default=None, help="Optional filename filter when resolving backup ids")

    restore_latest = subparsers.add_parser(
        "restore-latest-backup",
        help="Restore the newest backup for a specific target file.",
    )
    restore_latest.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    restore_latest.add_argument("--target-name", required=True, help="Filename to restore, e.g. SKILL.md")

    workspace = subparsers.add_parser(
        "compile-workspace",
        help="Compile a trial workspace dossier for a skill before mutation/evaluation.",
    )
    workspace.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    workspace.add_argument("--fixtures", default=None, help="Optional path to golden fixture JSON file")
    workspace.add_argument("--proposals", default=None, help="Optional path to proposal JSON file")
    workspace.add_argument("--logs-dir", default=None, help="Optional trace directory to summarize")
    workspace.add_argument("--markdown", action="store_true", help="Render the workspace as markdown instead of JSON")

    history = subparsers.add_parser(
        "backup-history",
        help="Show compact backup + operating-memory history for a target skill.",
    )
    history.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    history.add_argument("--limit", type=int, default=5, help="Number of recent trial history entries to show")

    suggest = subparsers.add_parser(
        "suggest-fixtures",
        help="Recommend reusable fixture templates from shared brain history.",
    )
    suggest.add_argument("--brain-dir", required=True, help="Path to the shared brain directory")
    suggest.add_argument("--fixture-name", required=True, help="Fixture name or idea to search for")
    suggest.add_argument("--limit", type=int, default=3, help="Max suggestions to return")

    dashboard = subparsers.add_parser(
        "brain-dashboard",
        help="Show an operator-facing shared-brain summary for the whole system or one skill.",
    )
    dashboard.add_argument("--brain-dir", required=True, help="Path to the shared brain directory")
    dashboard.add_argument("--skill-name", default=None, help="Optional skill name for focused detail")
    dashboard.add_argument("--limit", type=int, default=5, help="Max items per dashboard section")

    golden = subparsers.add_parser(
        "evaluate-golden",
        help="Evaluate a skill directly against golden fixtures using file/command probes.",
    )
    golden.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    golden.add_argument("--fixtures", required=True, help="Path to golden fixture JSON file")
    golden.add_argument(
        "--logs-dir",
        default=None,
        help="Optional directory to persist a structured evaluation trace JSON",
    )

    orchestration = subparsers.add_parser(
        "run-orchestration",
        help="Run a batch multi-skill orchestration from a JSON config file.",
    )
    orchestration.add_argument("--brain-dir", required=True, help="Path to the shared brain directory")
    orchestration.add_argument("--config", required=True, help="Path to orchestration config JSON file")
    orchestration.add_argument(
        "--logs-dir",
        default=None,
        help="Optional directory to persist orchestration summary logs",
    )

    checklist = subparsers.add_parser(
        "evaluate-checklist",
        help="Evaluate outputs against a checklist of yes/no questions.",
    )
    checklist.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    checklist.add_argument("--checklist", required=True, help="Path to checklist JSON file")
    checklist.add_argument(
        "--outputs",
        required=False,
        help="Path to JSON file with outputs to evaluate (dict or list)",
    )
    checklist.add_argument(
        "--logs-dir",
        default=None,
        help="Optional directory to persist a structured evaluation trace JSON",
    )

    hybrid = subparsers.add_parser(
        "evaluate-hybrid",
        help="Evaluate using both fixture and checklist modes (configurable gates).",
    )
    hybrid.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    hybrid.add_argument("--fixtures", required=False, help="Path to golden fixture JSON file")
    hybrid.add_argument("--checklist", required=False, help="Path to checklist JSON file")
    hybrid.add_argument(
        "--require-both",
        action="store_true",
        help="Require both fixture AND checklist to pass (default: either/or)",
    )
    hybrid.add_argument(
        "--outputs",
        required=False,
        help="Path to JSON file with outputs to evaluate",
    )
    hybrid.add_argument(
        "--logs-dir",
        default=None,
        help="Optional directory to persist a structured evaluation trace JSON",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scaffold-memory":
        result = scaffold_operating_memory(args.skill_path, force=args.force)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "inspect-backups":
        applier = SkillPatchApplier(args.skill_path)
        result = {
            "skill_path": args.skill_path,
            "backup_count": len(applier.list_backups()),
            "backups": [item.to_dict() for item in applier.inspect_backups(limit=args.limit, target_name=args.target_name)],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "restore-backup":
        applier = SkillPatchApplier(args.skill_path)
        resolved = applier.resolve_backup(args.backup, target_name=args.target_name)
        if resolved is None:
            print(json.dumps({
                "skill_path": args.skill_path,
                "backup": args.backup,
                "restored": False,
                "detail": "backup not found",
            }, indent=2, sort_keys=True))
            return 1
        report = applier.restore_backup(resolved)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0 if report.restored else 1

    if args.command == "restore-latest-backup":
        applier = SkillPatchApplier(args.skill_path)
        report = applier.restore_latest_backup(target_name=args.target_name)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0 if report.restored else 1

    if args.command == "backup-history":
        memory = OperatingMemory(args.skill_path)
        memory.ensure()
        history_path = Path(args.skill_path) / "data" / "run-history.jsonl"
        result = {
            "skill_path": args.skill_path,
            "backup_summary": memory.summarize_backups(),
            "operating_memory": memory.load_context(),
            "recent_trials": _read_jsonl_tail(history_path, limit=args.limit),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "suggest-fixtures":
        brain = SharedBrain(args.brain_dir)
        suggestions = brain.suggest_fixture_templates(args.fixture_name, limit=args.limit)
        result = {
            "brain_dir": str(args.brain_dir),
            "fixture_name": args.fixture_name,
            "suggestion_count": len(suggestions),
            "suggestions": [item.to_dict() for item in suggestions],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "brain-dashboard":
        brain = SharedBrain(args.brain_dir)
        result = brain.summarize_dashboard(args.skill_name, limit=args.limit)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-golden":
        fixtures = load_fixtures(args.fixtures)
        evaluation = GoldenEvaluator(fixtures).evaluate_all(
            evaluate_skill_fixtures(args.skill_path, fixtures)
        ).to_dict()
        result = {
            "skill_path": args.skill_path,
            "fixtures_path": str(args.fixtures),
            "evaluation": evaluation,
        }
        if args.logs_dir:
            result["trace_path"] = _write_trace(
                skill_path=args.skill_path,
                logs_dir=args.logs_dir,
                command="evaluate-golden",
                cli_metadata={
                    "fixtures_path": str(args.fixtures),
                },
                steps=[("evaluate", evaluation)],
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if evaluation.get("failed", 0) == 0 else 1

    if args.command == "run-orchestration":
        configs = _load_orchestration_configs(args.config)
        orchestrator = MultiSkillOrchestrator(args.brain_dir)
        run = orchestrator.run_orchestration(configs, logs_dir=args.logs_dir)
        result = {
            "brain_dir": str(args.brain_dir),
            "config_path": str(args.config),
            "skill_count": len(configs),
            "run": run.to_dict(),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-checklist":
        checklist = ChecklistLoader.load_from_file(args.checklist)
        evaluator = ChecklistEvaluator(checklist)

        if args.outputs:
            outputs = _load_json(args.outputs)
        else:
            outputs = {}

        evaluation = report = evaluator.evaluate_all(outputs).to_dict()
        result = {
            "skill_path": args.skill_path,
            "checklist_name": checklist.name,
            "evaluation": evaluation,
        }
        if args.logs_dir:
            result["trace_path"] = _write_trace(
                skill_path=args.skill_path,
                logs_dir=args.logs_dir,
                command="evaluate-checklist",
                cli_metadata={
                    "checklist_path": str(args.checklist),
                    "outputs_path": str(args.outputs) if args.outputs else None,
                },
                steps=[("evaluate", evaluation)],
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-hybrid":
        fixtures = None
        checklist = None

        if args.fixtures:
            fixtures = load_fixtures(args.fixtures)
        if args.checklist:
            checklist = ChecklistLoader.load_from_file(args.checklist)

        if not fixtures and not checklist:
            print(json.dumps({
                "error": "At least one of --fixtures or --checklist must be provided"
            }, indent=2, sort_keys=True))
            return 1

        stage = create_hybrid_evaluation_stage(
            fixtures=fixtures,
            checklist=checklist,
            require_both=args.require_both,
        )

        if args.outputs:
            outputs = _load_json(args.outputs)
            context = {"actual_outputs": outputs}
        else:
            context = {}

        result = stage(context)
        result["skill_path"] = args.skill_path
        result["require_both"] = args.require_both
        if args.logs_dir:
            result["trace_path"] = _write_trace(
                skill_path=args.skill_path,
                logs_dir=args.logs_dir,
                command="evaluate-hybrid",
                cli_metadata={
                    "fixtures_path": str(args.fixtures) if args.fixtures else None,
                    "checklist_path": str(args.checklist) if args.checklist else None,
                    "outputs_path": str(args.outputs) if args.outputs else None,
                    "require_both": args.require_both,
                },
                steps=[("evaluate", result)],
                status="ok" if "error" not in result else "error",
            )

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "compile-workspace":
        fixtures = load_fixtures(args.fixtures) if args.fixtures else []
        proposals = load_proposals(args.proposals) if args.proposals else []
        report = TrialWorkspaceCompiler(args.skill_path, logs_dir=args.logs_dir).compile(
            fixtures=fixtures,
            proposals=proposals,
        )
        if args.markdown:
            print(render_trial_workspace_markdown(report))
        else:
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.command != "trial":
        parser.error(f"unsupported command: {args.command}")

    fixtures = load_fixtures(args.fixtures)
    proposals = load_proposals(args.proposals)
    stage = create_safe_patch_trial_stage(
        fixtures,
        lambda skill_path, context, phase: evaluate_skill_fixtures(skill_path, fixtures),
        accepted_types=set(args.accepted_types),
        min_confidence=args.min_confidence,
        accepted_severities=set(args.accepted_severities),
        require_improvement=not args.allow_no_improvement,
    )

    result = stage(
        {
            "skill_path": args.skill_path,
            "amend": {"proposals": proposals},
        }
    )
    if args.logs_dir:
        result["trace_path"] = _write_trial_trace(
            skill_path=args.skill_path,
            logs_dir=args.logs_dir,
            fixtures_path=args.fixtures,
            proposals_path=args.proposals,
            result=result,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
