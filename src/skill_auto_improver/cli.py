from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .evaluator import GoldenFixture
from .loop import create_safe_patch_trial_stage, _update_trace_metadata
from .operating_memory import scaffold_operating_memory, OperatingMemory
from .applier import SkillPatchApplier
from .models import RunTrace, StepResult
from .logger import TraceLogger


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

        command_cwd = skill_root / probe.get("cwd", ".")
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


def _write_trial_trace(
    *,
    skill_path: str,
    logs_dir: str | Path,
    fixtures_path: str,
    proposals_path: str,
    result: dict[str, Any],
) -> str:
    trace = RunTrace(skill_path=str(skill_path))
    trace.metadata["cli"] = {
        "command": "trial",
        "fixtures_path": str(fixtures_path),
        "proposals_path": str(proposals_path),
    }

    for name, output in [
        ("before_eval", result.get("before_eval", {})),
        ("apply_trial", result),
        ("after_eval", result.get("after_eval", {})),
    ]:
        step = StepResult(name=name, output=output)
        step.finish()
        trace.add_step(step)
        _update_trace_metadata(trace, name, output)

    trace.complete(status="ok" if "error" not in result else "error")
    return str(TraceLogger(logs_dir).write(trace))


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

    history = subparsers.add_parser(
        "backup-history",
        help="Show compact backup + operating-memory history for a target skill.",
    )
    history.add_argument("--skill-path", required=True, help="Path to the target skill folder")
    history.add_argument("--limit", type=int, default=5, help="Number of recent trial history entries to show")

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
