from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.cli import load_fixtures, load_proposals, evaluate_skill_fixtures
from skill_auto_improver.loop import create_recent_run_observer_stage, create_trace_inspect_stage, create_safe_patch_trial_stage


EXAMPLE_ROOT = Path(__file__).resolve().parent / "real_skill_demo"


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _run_trial(*, skill_path: Path, fixtures_path: Path, proposals_path: Path) -> dict:
    fixtures = load_fixtures(fixtures_path)
    proposals = load_proposals(proposals_path)
    stage = create_safe_patch_trial_stage(
        fixtures,
        lambda current_skill_path, context, phase: evaluate_skill_fixtures(current_skill_path, fixtures),
        accepted_types={"instruction", "test_case"},
        min_confidence=0.0,
        accepted_severities={"info", "warning", "critical"},
        require_improvement=True,
    )
    return stage({
        "skill_path": str(skill_path),
        "amend": {"proposals": proposals},
    })


def run_demo(workspace: str | Path | None = None) -> dict:
    root_context = tempfile.TemporaryDirectory() if workspace is None else None
    root = Path(root_context.name) if root_context else Path(workspace)
    root.mkdir(parents=True, exist_ok=True)

    skill_path = root / "demo-skill"
    logs_dir = root / "runs"
    _copy_tree(EXAMPLE_ROOT / "skill", skill_path)

    fixtures_path = EXAMPLE_ROOT / "fixtures.json"
    safe_proposals_path = EXAMPLE_ROOT / "proposals-safe.json"
    regression_proposals_path = EXAMPLE_ROOT / "proposals-regression.json"

    safe_result = _run_trial(skill_path=skill_path, fixtures_path=fixtures_path, proposals_path=safe_proposals_path)
    safe_skill_text = (skill_path / "SKILL.md").read_text(encoding="utf-8")

    safe_trace = {
        "skill_path": str(skill_path),
        "run_id": "safe-demo-run",
        "status": "ok",
        "metadata": {
            "patch_trial": {
                "accepted": safe_result.get("accepted", False),
                "rolled_back": safe_result.get("rolled_back", False),
                "acceptance_reason": safe_result.get("acceptance_reason", ""),
                "recovered_count": safe_result.get("ab", {}).get("recovered_count", 0),
                "regressed_count": safe_result.get("ab", {}).get("regressed_count", 0),
                "applied_count": safe_result.get("apply", {}).get("applied_count", 0),
            }
        },
    }
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "safe-demo-run.json").write_text(json.dumps(safe_trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    observe_before_regression = create_recent_run_observer_stage(logs_dir, limit=10)({"skill_path": str(skill_path)})
    inspect_before_regression = create_trace_inspect_stage()({"observe": observe_before_regression})

    regression_result = _run_trial(skill_path=skill_path, fixtures_path=fixtures_path, proposals_path=regression_proposals_path)
    skill_text_after_regression = (skill_path / "SKILL.md").read_text(encoding="utf-8")

    regression_trace = {
        "skill_path": str(skill_path),
        "run_id": "regression-demo-run",
        "status": "ok",
        "metadata": {
            "patch_trial": {
                "accepted": regression_result.get("accepted", False),
                "rolled_back": regression_result.get("rolled_back", False),
                "acceptance_reason": regression_result.get("acceptance_reason", ""),
                "recovered_count": regression_result.get("ab", {}).get("recovered_count", 0),
                "regressed_count": regression_result.get("ab", {}).get("regressed_count", 0),
                "applied_count": regression_result.get("apply", {}).get("applied_count", 0),
            }
        },
    }
    (logs_dir / "regression-demo-run.json").write_text(json.dumps(regression_trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    observe_after_regression = create_recent_run_observer_stage(logs_dir, limit=10)({"skill_path": str(skill_path)})
    inspect_after_regression = create_trace_inspect_stage()({"observe": observe_after_regression})

    summary = {
        "workspace": str(root),
        "skill_path": str(skill_path),
        "logs_dir": str(logs_dir),
        "safe_trial": safe_result,
        "regression_trial": regression_result,
        "safe_skill_contains_formal_guidance": "Use the formal greeting." in safe_skill_text,
        "skill_preserved_after_rollback": skill_text_after_regression == safe_skill_text,
        "observe_before_regression": observe_before_regression,
        "inspect_before_regression": inspect_before_regression,
        "observe_after_regression": observe_after_regression,
        "inspect_after_regression": inspect_after_regression,
    }

    if root_context:
        summary["workspace"] = str(root)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
