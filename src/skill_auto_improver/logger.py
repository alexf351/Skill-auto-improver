from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from .models import RunTrace


def _collect_fixture_status_counts(trace: dict[str, Any]) -> dict[str, dict[str, int]]:
    counts = {
        "regressed": {},
        "recovered": {},
        "stable_fail": {},
    }

    for step in trace.get("steps", []):
        if not isinstance(step, dict):
            continue
        output = step.get("output") or {}
        comparisons = ((output.get("ab") or {}).get("comparisons") if isinstance(output, dict) else None) or output.get("comparisons") or []
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                continue
            fixture_name = str(comparison.get("fixture_name", "")).strip()
            status = str(comparison.get("status", "")).strip()
            if fixture_name and status in counts:
                bucket = counts[status]
                bucket[fixture_name] = bucket.get(fixture_name, 0) + 1

    return counts


def _top_fixture_counts(counts: dict[str, int], *, limit: int = 3) -> list[dict[str, Any]]:
    return [
        {"fixture_name": fixture_name, "count": count}
        for fixture_name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


class TraceLogger:
    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def write(self, trace: RunTrace) -> Path:
        path = self.root_dir / f"{trace.run_id}.json"
        path.write_text(json.dumps(trace.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def load_traces(root_dir: Path | str, *, limit: int | None = None) -> list[dict[str, Any]]:
    trace_dir = Path(root_dir)
    if not trace_dir.exists():
        return []

    files = sorted(trace_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if limit is not None:
        files = files[:limit]

    traces: list[dict[str, Any]] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_trace_path"] = str(path)
        traces.append(payload)
    return traces


def summarize_traces(
    traces: list[dict[str, Any]],
    *,
    skill_path: str | None = None,
) -> dict[str, Any]:
    filtered = [trace for trace in traces if not skill_path or trace.get("skill_path") == skill_path]
    acceptance_reasons: dict[str, int] = {}
    latest_failures: list[dict[str, Any]] = []
    latest_successes: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    total_regressions = 0
    total_recoveries = 0
    total_applied = 0
    fixture_status_totals = {
        "regressed": {},
        "recovered": {},
        "stable_fail": {},
    }

    for trace in filtered:
        status = trace.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        patch_trial = (trace.get("metadata") or {}).get("patch_trial") or {}
        fixture_counts = _collect_fixture_status_counts(trace)
        for status, counts in fixture_counts.items():
            aggregate = fixture_status_totals[status]
            for fixture_name, count in counts.items():
                aggregate[fixture_name] = aggregate.get(fixture_name, 0) + count

        if patch_trial:
            total_regressions += int(patch_trial.get("regressed_count", 0) or 0)
            total_recoveries += int(patch_trial.get("recovered_count", 0) or 0)
            total_applied += int(patch_trial.get("applied_count", 0) or 0)
            reason = patch_trial.get("acceptance_reason") or ""
            if reason:
                acceptance_reasons[reason] = acceptance_reasons.get(reason, 0) + 1

            compact = {
                "run_id": trace.get("run_id"),
                "finished_at": trace.get("finished_at"),
                "acceptance_reason": reason,
                "accepted": bool(patch_trial.get("accepted", False)),
                "rolled_back": bool(patch_trial.get("rolled_back", False)),
                "recovered_count": int(patch_trial.get("recovered_count", 0) or 0),
                "regressed_count": int(patch_trial.get("regressed_count", 0) or 0),
                "applied_count": int(patch_trial.get("applied_count", 0) or 0),
                "trace_path": trace.get("_trace_path"),
            }
            if compact["accepted"]:
                latest_successes.append(compact)
            else:
                latest_failures.append(compact)

    return {
        "trace_count": len(filtered),
        "status_counts": status_counts,
        "acceptance_reasons": acceptance_reasons,
        "total_regressions": total_regressions,
        "total_recoveries": total_recoveries,
        "total_applied": total_applied,
        "latest_failures": latest_failures[:3],
        "latest_successes": latest_successes[:3],
        "fixture_hotspots": {
            "regressed": _top_fixture_counts(fixture_status_totals["regressed"]),
            "recovered": _top_fixture_counts(fixture_status_totals["recovered"]),
            "stable_fail": _top_fixture_counts(fixture_status_totals["stable_fail"]),
        },
    }
