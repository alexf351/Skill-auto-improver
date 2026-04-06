from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluator import GoldenFixture
from .logger import load_traces, summarize_traces
from .operating_memory import OperatingMemory


@dataclass(slots=True)
class TrialWorkspaceReport:
    """Compiled, review-friendly workspace for a single improvement trial."""

    skill_path: str
    skill_summary: dict[str, Any]
    operating_memory: dict[str, Any]
    trace_summary: dict[str, Any]
    fixtures: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    policy_constraints: dict[str, Any]
    open_questions: list[str]
    candidate_changes: list[str]
    warnings: list[str]
    file_map: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_path": self.skill_path,
            "skill_summary": self.skill_summary,
            "operating_memory": self.operating_memory,
            "trace_summary": self.trace_summary,
            "fixtures": self.fixtures,
            "proposals": self.proposals,
            "policy_constraints": self.policy_constraints,
            "open_questions": self.open_questions,
            "candidate_changes": self.candidate_changes,
            "warnings": self.warnings,
            "file_map": self.file_map,
        }


class TrialWorkspaceCompiler:
    """Build a Karpathy-style ephemeral dossier before mutation/evaluation.

    The goal is not to mutate the skill. It's to compile scattered skill artifacts
    into one temporary, structured working set the improver can reason over.
    """

    def __init__(self, skill_path: str | Path, *, logs_dir: str | Path | None = None):
        self.skill_path = Path(skill_path)
        self.logs_dir = Path(logs_dir) if logs_dir is not None else None

    def compile(
        self,
        *,
        fixtures: list[GoldenFixture] | None = None,
        proposals: list[dict[str, Any]] | None = None,
        policy: dict[str, Any] | None = None,
        limit_files: int = 80,
    ) -> TrialWorkspaceReport:
        memory = OperatingMemory(self.skill_path)
        memory_context = memory.load_context() if self.skill_path.exists() else {}
        trace_summary = self._load_trace_summary()
        skill_summary = self._build_skill_summary()
        file_map = self._build_file_map(limit=limit_files)
        fixture_summaries = self._summarize_fixtures(fixtures or [])
        proposal_summaries = self._summarize_proposals(proposals or [])
        policy_constraints = self._normalize_policy(policy or {}, memory_context)
        warnings = self._build_warnings(
            skill_summary=skill_summary,
            trace_summary=trace_summary,
            fixture_summaries=fixture_summaries,
            proposal_summaries=proposal_summaries,
            policy_constraints=policy_constraints,
        )
        open_questions = self._build_open_questions(
            fixture_summaries=fixture_summaries,
            proposal_summaries=proposal_summaries,
            trace_summary=trace_summary,
            policy_constraints=policy_constraints,
        )
        candidate_changes = self._build_candidate_changes(proposal_summaries, warnings, trace_summary)

        return TrialWorkspaceReport(
            skill_path=str(self.skill_path),
            skill_summary=skill_summary,
            operating_memory=memory_context,
            trace_summary=trace_summary,
            fixtures=fixture_summaries,
            proposals=proposal_summaries,
            policy_constraints=policy_constraints,
            open_questions=open_questions,
            candidate_changes=candidate_changes,
            warnings=warnings,
            file_map=file_map,
        )

    def _load_trace_summary(self) -> dict[str, Any]:
        if not self.logs_dir:
            return {
                "trace_count": 0,
                "status_counts": {},
                "acceptance_reasons": {},
                "total_regressions": 0,
                "total_recoveries": 0,
                "total_applied": 0,
                "latest_failures": [],
                "latest_successes": [],
                "fixture_hotspots": {
                    "regressed": [],
                    "recovered": [],
                    "stable_fail": [],
                },
                "signals": ["no logs_dir provided"],
            }
        traces = load_traces(self.logs_dir, limit=12)
        summary = summarize_traces(traces, skill_path=str(self.skill_path))
        signals: list[str] = []
        if summary.get("trace_count", 0) == 0:
            signals.append("no prior trial traces")
        if summary.get("total_regressions", 0) > 0:
            signals.append("recent regressions present")
        if summary.get("acceptance_reasons", {}).get("no proposals applied"):
            signals.append("proposal pipeline produced no applied changes recently")
        if summary.get("total_recoveries", 0) > 0:
            signals.append("recent successful recoveries exist")
        hottest_regressed = (summary.get("fixture_hotspots") or {}).get("regressed", [])
        if hottest_regressed:
            top = hottest_regressed[0]
            signals.append(f"fixture hotspot: {top['fixture_name']} regressed {top['count']}x")
        summary["signals"] = signals
        return summary

    def _build_skill_summary(self) -> dict[str, Any]:
        exists = self.skill_path.exists()
        skill_file = self.skill_path / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8") if skill_file.exists() else ""
        lines = content.splitlines()
        return {
            "exists": exists,
            "skill_md_exists": skill_file.exists(),
            "line_count": len(lines),
            "char_count": len(content),
            "has_frontmatter": content.startswith("---"),
            "top_level_dirs": sorted([p.name for p in self.skill_path.iterdir() if p.is_dir()]) if exists else [],
            "top_level_files": sorted([p.name for p in self.skill_path.iterdir() if p.is_file()]) if exists else [],
        }

    def _build_file_map(self, *, limit: int) -> list[dict[str, Any]]:
        if not self.skill_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(self.skill_path.rglob("*")):
            if len(entries) >= limit:
                break
            rel = path.relative_to(self.skill_path)
            if any(part.startswith(".") and part != ".skill-auto-improver" for part in rel.parts):
                continue
            if path.is_dir():
                continue
            entry = {
                "path": rel.as_posix(),
                "size_bytes": path.stat().st_size,
                "kind": self._infer_kind(rel),
            }
            if path.suffix == ".md":
                entry["headings"] = self._extract_headings(path)
            entries.append(entry)
        return entries

    def _summarize_fixtures(self, fixtures: list[GoldenFixture]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for fixture in fixtures:
            probe = fixture.input_data or {}
            probe_mode = "path" if "path" in probe else "command" if "command" in probe else "unknown"
            summaries.append(
                {
                    "name": fixture.name,
                    "probe_mode": probe_mode,
                    "input_keys": sorted(probe.keys()),
                    "expected_keys": sorted((fixture.expected_output or {}).keys()),
                }
            )
        return summaries

    def _summarize_proposals(self, proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for proposal in proposals:
            content = proposal.get("content") or {}
            summaries.append(
                {
                    "fixture_name": proposal.get("fixture_name", ""),
                    "type": proposal.get("type", ""),
                    "severity": proposal.get("severity", "info"),
                    "confidence": proposal.get("confidence", 0.0),
                    "content_keys": sorted(content.keys()) if isinstance(content, dict) else [],
                }
            )
        return summaries

    def _normalize_policy(self, policy: dict[str, Any], memory_context: dict[str, Any]) -> dict[str, Any]:
        proposal_hints = memory_context.get("proposal_hints") or {}
        return {
            "min_confidence": policy.get("min_confidence"),
            "accepted_severities": policy.get("accepted_severities"),
            "fixture_policy_count": len((policy.get("fixture_policies") or {})),
            "protect_promoted_fixtures": policy.get("protect_promoted_fixtures"),
            "rollback_on_history_regression": policy.get("rollback_on_history_regression"),
            "boost_terms": proposal_hints.get("boost_terms", []),
            "avoid_terms": proposal_hints.get("avoid_terms", []),
            "preferred_types": proposal_hints.get("prefer_types", []),
        }

    def _build_warnings(
        self,
        *,
        skill_summary: dict[str, Any],
        trace_summary: dict[str, Any],
        fixture_summaries: list[dict[str, Any]],
        proposal_summaries: list[dict[str, Any]],
        policy_constraints: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        if not skill_summary.get("skill_md_exists"):
            warnings.append("missing SKILL.md")
        if trace_summary.get("acceptance_reasons", {}).get("no proposals applied"):
            warnings.append("recent trials ended with no proposals applied")
        if trace_summary.get("total_regressions", 0) > 0:
            warnings.append("recent regressions detected in trial history")
        hottest_regressed = (trace_summary.get("fixture_hotspots") or {}).get("regressed", [])
        if hottest_regressed:
            top = hottest_regressed[0]
            warnings.append(f"fixture hotspot '{top['fixture_name']}' regressed repeatedly in recent traces")
        if fixture_summaries and not proposal_summaries:
            warnings.append("fixtures exist but no proposals supplied")
        if proposal_summaries and not fixture_summaries:
            warnings.append("proposals exist without fixture context")
        if policy_constraints.get("min_confidence") and all(
            (proposal.get("confidence") or 0.0) < float(policy_constraints["min_confidence"])
            for proposal in proposal_summaries
        ):
            warnings.append("all proposals currently sit below the active confidence floor")
        return warnings

    def _build_open_questions(
        self,
        *,
        fixture_summaries: list[dict[str, Any]],
        proposal_summaries: list[dict[str, Any]],
        trace_summary: dict[str, Any],
        policy_constraints: dict[str, Any],
    ) -> list[str]:
        questions: list[str] = []
        if not fixture_summaries:
            questions.append("What concrete fixtures should define success for this skill?")
        if not proposal_summaries:
            questions.append("What candidate changes should be generated or loaded before mutation?")
        if trace_summary.get("acceptance_reasons", {}).get("no proposals applied"):
            questions.append("Why are recent runs producing zero applied changes: missing proposals, policy mismatch, or unsupported types?")
        if policy_constraints.get("fixture_policy_count", 0) > 0:
            questions.append("Do fixture-level policies still match the current proposal mix and skill structure?")
        hottest_regressed = (trace_summary.get("fixture_hotspots") or {}).get("regressed", [])
        if hottest_regressed:
            top = hottest_regressed[0]
            questions.append(f"What narrower fix or extra regression coverage would stop hotspot fixture '{top['fixture_name']}' from re-breaking?")
        return questions

    def _build_candidate_changes(
        self,
        proposal_summaries: list[dict[str, Any]],
        warnings: list[str],
        trace_summary: dict[str, Any],
    ) -> list[str]:
        candidates = [
            f"{proposal['fixture_name'] or 'global'}:{proposal['type']} ({proposal['severity']}, conf={proposal['confidence']:.2f})"
            for proposal in proposal_summaries[:10]
        ]
        if not candidates and "recent trials ended with no proposals applied" in warnings:
            candidates.append("Investigate proposal generation/apply pipeline mismatch before new mutations")
        if trace_summary.get("total_regressions", 0) > 0:
            candidates.append("Bias toward narrower, test-backed changes because regressions recently occurred")
        hottest_regressed = (trace_summary.get("fixture_hotspots") or {}).get("regressed", [])
        if hottest_regressed:
            top = hottest_regressed[0]
            candidates.append(f"Prioritize a fixture-specific fix for {top['fixture_name']} before broader skill rewrites")
        return candidates

    def _extract_headings(self, path: Path, *, limit: int = 6) -> list[str]:
        headings: list[str] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    headings.append(stripped)
                if len(headings) >= limit:
                    break
        except Exception:
            return []
        return headings

    def _infer_kind(self, relative_path: Path) -> str:
        parts = relative_path.parts
        if relative_path.name == "SKILL.md":
            return "skill_definition"
        if "data" in parts:
            return "data"
        if "references" in parts or "docs" in parts:
            return "reference"
        if "scripts" in parts:
            return "script"
        if relative_path.suffix == ".md":
            return "markdown"
        if relative_path.suffix == ".json":
            return "json"
        return relative_path.suffix.lstrip(".") or "file"


def render_trial_workspace_markdown(report: TrialWorkspaceReport) -> str:
    """Render the compiled workspace as a readable markdown memo."""
    lines = [
        f"# Trial Workspace — {report.skill_path}",
        "",
        "## Skill Summary",
        f"- SKILL.md present: {report.skill_summary.get('skill_md_exists')}",
        f"- Lines: {report.skill_summary.get('line_count')}",
        f"- Directories: {', '.join(report.skill_summary.get('top_level_dirs', [])) or '(none)'}",
        f"- Files: {', '.join(report.skill_summary.get('top_level_files', [])) or '(none)'}",
        "",
        "## Trace Summary",
        f"- Trace count: {report.trace_summary.get('trace_count', 0)}",
        f"- Acceptance reasons: {json.dumps(report.trace_summary.get('acceptance_reasons', {}), sort_keys=True)}",
        f"- Signals: {', '.join(report.trace_summary.get('signals', [])) or '(none)'}",
        "",
        "## Policy Constraints",
        f"- Min confidence: {report.policy_constraints.get('min_confidence')}",
        f"- Accepted severities: {report.policy_constraints.get('accepted_severities')}",
        f"- Preferred proposal types: {', '.join(report.policy_constraints.get('preferred_types', [])) or '(none)'}",
        "",
        "## Warnings",
    ]
    if report.warnings:
        lines.extend([f"- {warning}" for warning in report.warnings])
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Open Questions",
    ])
    if report.open_questions:
        lines.extend([f"- {question}" for question in report.open_questions])
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Candidate Changes",
    ])
    if report.candidate_changes:
        lines.extend([f"- {candidate}" for candidate in report.candidate_changes])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"
