from .loop import (
    SkillAutoImprover,
    run_once,
    create_ab_evaluation_stage,
    create_patch_apply_stage,
    create_safe_patch_trial_stage,
    create_recent_run_observer_stage,
    create_trace_inspect_stage,
    create_trial_workspace_stage,
)
from .ab_evaluator import ABEvaluator, ABReport
from .applier import SkillPatchApplier, ApplyReport, BackupEntry, RestoreReport


def cli_main(argv=None):
    from .cli import main

    return main(argv)

__all__ = [
    "SkillAutoImprover",
    "run_once",
    "create_ab_evaluation_stage",
    "create_patch_apply_stage",
    "create_safe_patch_trial_stage",
    "create_recent_run_observer_stage",
    "create_trace_inspect_stage",
    "create_trial_workspace_stage",
    "ABEvaluator",
    "ABReport",
    "SkillPatchApplier",
    "ApplyReport",
    "BackupEntry",
    "RestoreReport",
    "cli_main",
]
