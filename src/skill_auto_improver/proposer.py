"""
Amendment Proposal Engine

Generates structured patch proposals from failing golden test cases.
Analyzes deltas to suggest:
- Instruction rewrites (guidance updates to SKILL.md)
- Supporting artifact updates (references/checklists beyond SKILL.md)
- Test case additions (new golden fixtures to prevent regression)
- Reasoning suggestions (how to fix the root cause)

Brain-aware proposal generation:
- Load promotion wisdom from shared brain to boost confidence
- Use regression patterns to strengthen warnings
- Rank proposals based on what's worked across skills
- Apply cross-skill lessons to fixture-specific guidance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .evaluator import TestResult, GoldenFixture

if TYPE_CHECKING:
    from .shared_brain import SharedBrain


@dataclass(slots=True)
class PatchProposal:
    """A single actionable patch suggestion."""
    type: str  # "instruction", "artifact", "test_case", "reasoning"
    description: str
    content: dict[str, Any]
    fixture_name: str
    severity: str = "info"  # "info", "warning", "critical"
    confidence: float = 0.8  # 0.0-1.0: how confident in this proposal


@dataclass(slots=True)
class ProposalReport:
    """Summary of all amendment proposals generated from a test run."""
    total_failures: int
    proposals: list[PatchProposal] = field(default_factory=list)
    memory_context: dict[str, Any] | None = None

    @property
    def total_proposals(self) -> int:
        return len(self.proposals)

    def proposals_by_type(self, proposal_type: str) -> list[PatchProposal]:
        return [p for p in self.proposals if p.type == proposal_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_failures": self.total_failures,
            "total_proposals": self.total_proposals,
            "proposals": [
                {
                    "fixture_name": p.fixture_name,
                    "type": p.type,
                    "description": p.description,
                    "content": p.content,
                    "severity": p.severity,
                    "confidence": p.confidence,
                }
                for p in self.proposals
            ],
            "memory_context": self.memory_context,
        }


class ProposalEngine:
    """
    Analyzes failing test cases and generates patch proposals.

    Takes TestResults with deltas and generates:
    1. Instruction proposals: guidance changes to fix the issue
    2. Supporting artifact proposals: reference/checklist changes beyond SKILL.md
    3. Test case proposals: new fixtures to prevent regression
    4. Reasoning proposals: diagnostic hints for the amend stage
    
    With optional brain integration:
    - Boosts confidence scores using promotion wisdom
    - Applies regression prevention patterns
    - Reorders proposals based on cross-skill success
    - Enriches fixtures with cross-skill lessons
    """

    def __init__(self, brain: SharedBrain | None = None):
        """
        Initialize proposal engine with optional shared brain.
        
        Args:
            brain: Optional SharedBrain instance for cross-skill learning.
                   If provided, proposals will be enhanced with promotion wisdom,
                   regression patterns, and cross-skill insights.
        """
        self.brain = brain

    def generate_proposals(
        self,
        failed_results: list[TestResult],
        original_fixtures: list[GoldenFixture] | None = None,
        operating_memory: dict[str, Any] | None = None,
        inspect_context: dict[str, Any] | None = None,
        skill_path: str | Path | None = None,
        skill_name: str | None = None,
    ) -> ProposalReport:
        """
        Generate proposals with optional brain context.
        
        Args:
            failed_results: Test results that failed
            original_fixtures: Original golden fixtures
            operating_memory: Per-skill operating memory
            skill_path: Path to the skill root
            skill_name: Name of the skill being improved (for brain queries)
        
        Returns:
            ProposalReport with brain-enhanced proposals if brain is available
        """
        memory_context = operating_memory or {}
        skill_profile = self._skill_structure_profile(skill_path)
        memory_context = {
            **memory_context,
            "skill_profile": skill_profile,
        }
        if inspect_context:
            memory_context["inspect_context"] = inspect_context
            memory_context["inspect_focus"] = self._extract_inspect_focus(inspect_context)
        
        # Enrich memory context with brain wisdom if available
        if self.brain and skill_name:
            brain_context = self._load_brain_context(skill_name)
            memory_context.update(brain_context)
        
        report = ProposalReport(total_failures=len(failed_results), memory_context=memory_context)

        for result in failed_results:
            instr_proposal = self._propose_instruction_fix(result, memory_context)
            if instr_proposal:
                report.proposals.append(instr_proposal)

            artifact_proposal = self._propose_supporting_artifact(result, memory_context)
            if artifact_proposal:
                report.proposals.append(artifact_proposal)

            test_proposal = self._propose_test_addition(result, memory_context)
            if test_proposal:
                report.proposals.append(test_proposal)

            reasoning_proposal = self._propose_reasoning(result, memory_context)
            if reasoning_proposal:
                report.proposals.append(reasoning_proposal)

        report.proposals.sort(
            key=lambda proposal: self._proposal_sort_key(proposal, memory_context)
        )

        return report

    def _propose_instruction_fix(self, result: TestResult, memory_context: dict[str, Any]) -> PatchProposal | None:
        if not result.delta:
            return None

        mismatches = list(result.delta.keys())
        mismatch_str = ", ".join(mismatches)
        hints = self._memory_hints(result.fixture_name, memory_context)
        fixture_profile = self._fixture_profile(result.fixture_name, memory_context)

        description = (
            f"Update skill instructions: fields [{mismatch_str}] don't match expected output. "
            f"Review SKILL.md guidance for {result.fixture_name}."
        )
        if self._is_inspect_hotspot(result.fixture_name, memory_context):
            description += " Keep the patch fixture-local and avoid broad skill-wide rewrites."
        if hints:
            description += f" Memory hints: {hints}"

        confidence = self._base_confidence(0.85, result.fixture_name, "instruction", memory_context)
        severity = "critical" if self._fixture_is_regression_prone(result.fixture_name, memory_context) or len(mismatches) > 1 else "warning"
        if fixture_profile.get("policy", {}).get("accepted_severities") == ["critical"]:
            severity = "critical"

        content = {
            "context": "Instruction mismatch detected",
            "test_name": result.fixture_name,
            "mismatched_fields": mismatches,
            "suggestion": f"Review and tighten instructions for {result.fixture_name}",
            "memory_hints": hints,
            "memory_bias": self._bias_detail(result.fixture_name, memory_context),
            "scope": self._proposal_scope(result.fixture_name, memory_context),
        }

        return PatchProposal(
            type="instruction",
            description=description,
            content=content,
            fixture_name=result.fixture_name,
            severity=severity,
            confidence=confidence,
        )

    def _propose_supporting_artifact(self, result: TestResult, memory_context: dict[str, Any]) -> PatchProposal | None:
        if not result.delta:
            return None

        promotion_profile = self._promotion_profile(result.fixture_name, memory_context)
        fixture_profile = self._fixture_profile(result.fixture_name, memory_context)
        skill_profile = memory_context.get("skill_profile") or {}
        should_emit = (
            promotion_profile.get("historically_protected")
            or fixture_profile.get("regression_prone")
            or bool(skill_profile.get("has_supporting_assets"))
        )
        if not should_emit:
            return None

        mismatches = list(result.delta.keys())
        hints = self._memory_hints(result.fixture_name, memory_context)
        artifact_plan = self._choose_artifact_plan(
            fixture_name=result.fixture_name,
            mismatches=mismatches,
            skill_profile=skill_profile,
            hints=hints,
        )

        description = (
            f"Add supporting artifact for {result.fixture_name} so risky behavior is documented in a structure-aware location. "
            f"Target: {artifact_plan['target_path']}."
        )
        if self._is_inspect_hotspot(result.fixture_name, memory_context):
            description += " Use it to constrain the next fix to this hotspot before touching adjacent fixtures."
        content = {
            "target_path": artifact_plan["target_path"],
            "format": artifact_plan["format"],
            "section_title": artifact_plan["section_title"],
            "body": artifact_plan["body"],
            "structure_reason": artifact_plan["structure_reason"],
            "memory_hints": hints,
            "memory_bias": self._bias_detail(result.fixture_name, memory_context),
            "skill_profile": skill_profile,
            "scope": self._proposal_scope(result.fixture_name, memory_context),
        }
        return PatchProposal(
            type="artifact",
            description=description,
            content=content,
            fixture_name=result.fixture_name,
            severity="warning" if (promotion_profile.get("historically_protected") or fixture_profile.get("regression_prone")) else "info",
            confidence=self._base_confidence(0.88, result.fixture_name, "artifact", memory_context),
        )

    def _propose_test_addition(self, result: TestResult, memory_context: dict[str, Any]) -> PatchProposal | None:
        new_fixture = {
            "name": f"{result.fixture_name}_regression",
            "input_data": {},
            "expected_output": result.expected,
            "tags": ["regression", "edge-case"],
        }
        if self._fixture_is_regression_prone(result.fixture_name, memory_context):
            new_fixture["tags"].append("memory-priority")

        description = (
            f"Add regression test for {result.fixture_name}. "
            f"Current output doesn't match expected; lock in the expected behavior."
        )
        if self._is_inspect_hotspot(result.fixture_name, memory_context):
            description += " Prioritize this hotspot fixture before adding broader coverage."
        hints = self._memory_hints(result.fixture_name, memory_context)
        if hints:
            description += f" Memory hints: {hints}"

        content = {
            "fixture": new_fixture,
            "reason": "Prevent regression of this failure",
            "memory_hints": hints,
            "memory_bias": self._bias_detail(result.fixture_name, memory_context),
            "scope": self._proposal_scope(result.fixture_name, memory_context),
        }

        confidence = self._base_confidence(0.90, result.fixture_name, "test_case", memory_context)
        severity = "warning" if self._fixture_is_regression_prone(result.fixture_name, memory_context) else "info"

        return PatchProposal(
            type="test_case",
            description=description,
            content=content,
            fixture_name=result.fixture_name,
            severity=severity,
            confidence=confidence,
        )

    def _propose_reasoning(self, result: TestResult, memory_context: dict[str, Any]) -> PatchProposal | None:
        mismatch_count = len(result.delta)
        if mismatch_count == 0:
            return None

        hints = self._memory_hints(result.fixture_name, memory_context)
        reasoning = (
            f"Expected output has {mismatch_count} field(s) that differ from actual. "
            f"Root cause likely: skill logic doesn't implement full spec for {result.fixture_name}. "
            f"Review delta: {result.delta}"
        )
        if hints:
            reasoning += f" Memory hints: {hints}"

        content = {
            "root_cause_hypothesis": f"Incomplete implementation of {result.fixture_name}",
            "mismatch_count": mismatch_count,
            "delta_summary": result.delta,
            "next_step": "Amend the skill code or instructions to match expected output",
            "memory_hints": hints,
            "memory_bias": self._bias_detail(result.fixture_name, memory_context),
            "scope": self._proposal_scope(result.fixture_name, memory_context),
        }

        severity = "critical" if mismatch_count > 1 or self._fixture_is_regression_prone(result.fixture_name, memory_context) else "warning"
        confidence = self._base_confidence(0.80, result.fixture_name, "reasoning", memory_context)

        return PatchProposal(
            type="reasoning",
            description=reasoning,
            content=content,
            fixture_name=result.fixture_name,
            severity=severity,
            confidence=confidence,
        )

    def _memory_hints(self, fixture_name: str, memory_context: dict[str, Any]) -> str:
        profile = self._fixture_profile(fixture_name, memory_context)
        lesson = profile.get("lessons", [])[-1] if profile.get("lessons") else next((item for item in reversed(memory_context.get("lessons", [])) if fixture_name in item), "")
        gotcha = profile.get("gotchas", [])[-1] if profile.get("gotchas") else next((item for item in reversed(memory_context.get("gotchas", [])) if fixture_name in item), "")
        boosts = profile.get("boost_terms", []) or (memory_context.get("proposal_hints") or {}).get("boost_terms", [])
        avoids = profile.get("avoid_terms", []) or (memory_context.get("proposal_hints") or {}).get("avoid_terms", [])

        hints: list[str] = []
        if lesson:
            hints.append(f"lesson={lesson}")
        if gotcha:
            hints.append(f"gotcha={gotcha}")
        if boosts:
            hints.append("prefer=" + ", ".join(boosts[:3]))
        if avoids:
            hints.append("avoid=" + ", ".join(avoids[:3]))
        
        # Add cross-skill promotion wisdom if available
        if memory_context.get("brain_context") and memory_context.get("promotion_wisdom"):
            for wisdom in memory_context["promotion_wisdom"]:
                if fixture_name == wisdom.get("fixture_name"):
                    if wisdom.get("shared_lessons"):
                        lessons_str = "; ".join(wisdom["shared_lessons"][:2])
                        hints.append(f"cross_skill_lesson={lessons_str}")
                    skills_str = ", ".join(wisdom.get("skills_successful", [])[:3])
                    if skills_str:
                        hints.append(f"promoted_in={skills_str}")
        
        return "; ".join(hints)

    def _fixture_is_regression_prone(self, fixture_name: str, memory_context: dict[str, Any]) -> bool:
        boosted = set((memory_context.get("proposal_hints") or {}).get("boosted_fixtures", []))
        profile = self._fixture_profile(fixture_name, memory_context)
        promotion_profile = self._promotion_profile(fixture_name, memory_context)
        return fixture_name in boosted or bool(profile.get("regression_prone")) or bool(promotion_profile.get("historically_protected"))

    def _base_confidence(self, base: float, fixture_name: str, proposal_type: str, memory_context: dict[str, Any]) -> float:
        confidence = base
        profile = self._fixture_profile(fixture_name, memory_context)
        preferred_types = set(profile.get("prefer_types", []) or (memory_context.get("proposal_hints") or {}).get("prefer_types", []))
        if proposal_type in preferred_types:
            confidence += 0.03
        if self._fixture_is_regression_prone(fixture_name, memory_context):
            confidence += 0.04
        history = profile.get("history", {})
        if history.get("rollback_count", 0) > 0:
            confidence += 0.02
        if history.get("recovery_count", 0) > 0 and proposal_type in {"instruction", "test_case", "artifact"}:
            confidence += 0.01
        promotion_profile = self._promotion_profile(fixture_name, memory_context)
        if promotion_profile.get("historically_protected") and proposal_type in {"test_case", "artifact"}:
            confidence += 0.04
        if promotion_profile.get("historically_protected") and proposal_type == "instruction":
            confidence -= 0.02
        
        # Boost confidence based on brain promotion wisdom
        if memory_context.get("brain_context") and memory_context.get("promotion_wisdom"):
            for wisdom in memory_context["promotion_wisdom"]:
                if fixture_name == wisdom.get("fixture_name"):
                    # If this exact fixture pattern was promoted elsewhere, boost confidence
                    confidence += wisdom.get("confidence", 0.8) * 0.02
                    if proposal_type in wisdom.get("proposal_type_sequence", []):
                        confidence += 0.03
        
        # Apply skill mastery learning to proposal type confidence
        if memory_context.get("skill_mastery"):
            mastery = memory_context["skill_mastery"]
            if proposal_type == mastery.get("most_useful_proposal_type"):
                confidence += 0.02
        
        fixture_min_confidence = profile.get("policy", {}).get("min_confidence")
        if fixture_min_confidence not in (None, ""):
            confidence = max(confidence, min(float(fixture_min_confidence), 0.99))
        return min(max(confidence, 0.0), 0.99)

    def _bias_detail(self, fixture_name: str, memory_context: dict[str, Any]) -> dict[str, Any]:
        profile = self._fixture_profile(fixture_name, memory_context)
        return {
            "fixture_is_regression_prone": self._fixture_is_regression_prone(fixture_name, memory_context),
            "preferred_types": profile.get("prefer_types", []) or (memory_context.get("proposal_hints") or {}).get("prefer_types", []),
            "fixture_profile": profile,
            "promotion_profile": self._promotion_profile(fixture_name, memory_context),
            "history": memory_context.get("history", {}),
            "skill_profile": memory_context.get("skill_profile", {}),
        }

    def _fixture_profile(self, fixture_name: str, memory_context: dict[str, Any]) -> dict[str, Any]:
        return ((memory_context.get("proposal_hints") or {}).get("fixture_profiles") or {}).get(fixture_name, {})

    def _promotion_profile(self, fixture_name: str, memory_context: dict[str, Any]) -> dict[str, Any]:
        return ((memory_context.get("proposal_hints") or {}).get("promotion_profiles") or {}).get(fixture_name, {})

    def _proposal_sort_key(self, proposal: PatchProposal, memory_context: dict[str, Any]) -> tuple[int, int, int, int, int, float]:
        inspect_focus = self._inspect_focus_map(memory_context)
        preferred_types = set(
            self._fixture_profile(proposal.fixture_name, memory_context).get("prefer_types", [])
            or (memory_context.get("proposal_hints") or {}).get("prefer_types", [])
        )
        promotion_profile = self._promotion_profile(proposal.fixture_name, memory_context)
        hotspot_priority = 0 if proposal.fixture_name in inspect_focus.get("hotspot_fixtures", set()) else 1
        regression_priority = 0 if self._fixture_is_regression_prone(proposal.fixture_name, memory_context) else 1
        protected_priority = 0 if promotion_profile.get("historically_protected") else 1
        if promotion_profile.get("historically_protected"):
            type_priority_map = {"test_case": 0, "artifact": 1, "instruction": 2, "reasoning": 3}
        else:
            type_priority_map = {"instruction": 0, "artifact": 1, "test_case": 2, "reasoning": 3}
        if proposal.fixture_name in inspect_focus.get("hotspot_fixtures", set()):
            type_priority_map = {"test_case": 0, "artifact": 1, "instruction": 2, "reasoning": 3}
        preferred_priority = 0 if proposal.type in preferred_types else 1
        return (hotspot_priority, regression_priority, protected_priority, preferred_priority, type_priority_map.get(proposal.type, 9), -proposal.confidence)

    def _extract_inspect_focus(self, inspect_context: dict[str, Any]) -> dict[str, Any]:
        hotspot_fixtures: list[str] = []
        fixture_hotspots = inspect_context.get("fixture_hotspots") or {}
        for bucket in ("regressed", "stable_fail"):
            for item in fixture_hotspots.get(bucket, []):
                fixture_name = item.get("fixture_name")
                if fixture_name and fixture_name not in hotspot_fixtures:
                    hotspot_fixtures.append(fixture_name)
        return {
            "hotspot_fixtures": hotspot_fixtures,
            "priorities": list(inspect_context.get("priorities") or []),
            "hypotheses": list(inspect_context.get("hypotheses") or []),
        }

    def _inspect_focus_map(self, memory_context: dict[str, Any]) -> dict[str, Any]:
        inspect_focus = memory_context.get("inspect_focus") or {}
        hotspot_fixtures = inspect_focus.get("hotspot_fixtures") or []
        return {
            **inspect_focus,
            "hotspot_fixtures": set(hotspot_fixtures),
        }

    def _is_inspect_hotspot(self, fixture_name: str, memory_context: dict[str, Any]) -> bool:
        return fixture_name in self._inspect_focus_map(memory_context).get("hotspot_fixtures", set())

    def _proposal_scope(self, fixture_name: str, memory_context: dict[str, Any]) -> dict[str, Any]:
        inspect_focus = self._inspect_focus_map(memory_context)
        is_hotspot = fixture_name in inspect_focus.get("hotspot_fixtures", set())
        return {
            "mode": "fixture_hotspot" if is_hotspot else "normal",
            "fixture_local_only": is_hotspot,
            "focused_fixture": fixture_name if is_hotspot else None,
            "hotspot_fixtures": sorted(inspect_focus.get("hotspot_fixtures", set())),
        }

    def _skill_structure_profile(self, skill_path: str | Path | None) -> dict[str, Any]:
        if not skill_path:
            return {
                "skill_path": None,
                "existing_dirs": [],
                "existing_files": [],
                "supporting_asset_dirs": [],
                "has_supporting_assets": False,
                "preferred_artifact_dir": "references/auto-improver",
                "artifact_kind": "reference_note",
            }

        root = Path(skill_path)
        existing_dirs: list[str] = []
        existing_files: list[str] = []
        for relative in [
            "references",
            "docs",
            "scripts",
            "checklists",
            "examples",
            "assets",
            "references/auto-improver",
            "docs/auto-improver",
            "checklists/auto-improver",
            "scripts/auto-improver",
        ]:
            if (root / relative).exists():
                if (root / relative).is_dir():
                    existing_dirs.append(relative)
                else:
                    existing_files.append(relative)

        if (root / "references").exists():
            preferred_artifact_dir = "references/auto-improver"
            artifact_kind = "reference_note"
        elif (root / "docs").exists():
            preferred_artifact_dir = "docs/auto-improver"
            artifact_kind = "reference_note"
        elif (root / "checklists").exists():
            preferred_artifact_dir = "checklists/auto-improver"
            artifact_kind = "checklist"
        elif (root / "scripts").exists():
            preferred_artifact_dir = "scripts/auto-improver"
            artifact_kind = "checklist"
        else:
            preferred_artifact_dir = "references/auto-improver"
            artifact_kind = "reference_note"

        supporting_asset_dirs = [item for item in existing_dirs if item.split("/")[0] in {"references", "docs", "scripts", "checklists", "examples"}]
        return {
            "skill_path": str(root),
            "existing_dirs": sorted(existing_dirs),
            "existing_files": sorted(existing_files),
            "supporting_asset_dirs": sorted(supporting_asset_dirs),
            "has_supporting_assets": bool(supporting_asset_dirs),
            "preferred_artifact_dir": preferred_artifact_dir,
            "artifact_kind": artifact_kind,
        }

    def _choose_artifact_plan(
        self,
        *,
        fixture_name: str,
        mismatches: list[str],
        skill_profile: dict[str, Any],
        hints: str,
    ) -> dict[str, str]:
        preferred_dir = skill_profile.get("preferred_artifact_dir", "references/auto-improver")
        artifact_kind = skill_profile.get("artifact_kind", "reference_note")
        target_path = f"{preferred_dir}/{fixture_name}.md"
        field_summary = ", ".join(mismatches) if mismatches else "n/a"
        bullets = [
            f"Protect fixture `{fixture_name}` before broad edits land.",
            f"Re-check expected fields: {field_summary}.",
            "Validate against promoted behavior before accepting adjacent changes.",
            "Prefer the smallest artifact/instruction delta that recovers the fixture.",
        ]
        if hints:
            bullets.append(f"Memory hints: {hints}")

        if artifact_kind == "checklist":
            body = "\n".join(f"- [ ] {item}" for item in bullets)
            structure_reason = f"skill already uses {preferred_dir.split('/')[0]}/-style supporting assets, so emit an operator checklist"
            section_title = f"Auto-Improver checklist for {fixture_name}"
            format_name = "markdown_checklist"
        else:
            body = "\n".join(f"- {item}" for item in bullets)
            structure_reason = f"skill already has supporting docs under {preferred_dir.split('/')[0]}/, so append a reference note there"
            section_title = f"Auto-Improver safeguard for {fixture_name}"
            format_name = "markdown_append"

        return {
            "target_path": target_path,
            "format": format_name,
            "section_title": section_title,
            "body": body,
            "structure_reason": structure_reason,
        }

    def _load_brain_context(self, skill_name: str) -> dict[str, Any]:
        """
        Load cross-skill context from shared brain.
        
        Extracts:
        - Promotion wisdom for fixtures this skill could benefit from
        - Regression patterns affecting similar skills
        - Core directives that apply to this skill
        - Fixture library suggestions
        - Skill mastery learnings
        
        Args:
            skill_name: Name of the skill being improved
        
        Returns:
            Dictionary with enriched cross-skill context
        """
        if not self.brain:
            return {}
        
        context: dict[str, Any] = {
            "brain_context": True,
            "skill_name": skill_name,
            "promotion_wisdom": [],
            "regression_patterns": [],
            "core_directives": [],
            "skill_mastery": None,
            "library_suggestions": [],
        }
        
        try:
            # Load applicable core directives
            directives = self.brain.get_directives_for_skill(skill_name)
            context["core_directives"] = [
                {
                    "id": d.id,
                    "title": d.title,
                    "description": d.description,
                    "auto_apply": d.auto_apply,
                }
                for d in directives
            ]
            
            # Load skill mastery
            mastery = self.brain.get_or_create_skill_mastery(skill_name)
            context["skill_mastery"] = {
                "skill_name": mastery.skill_name,
                "trial_count": mastery.trial_count,
                "success_rate": mastery.success_rate,
                "most_useful_proposal_type": mastery.most_useful_proposal_type,
                "common_issues": mastery.common_issues,
            }
            
            # Load regression patterns for this skill
            patterns = self.brain.get_regression_patterns_for_skill(skill_name)
            context["regression_patterns"] = [
                {
                    "id": p.id,
                    "pattern_name": p.pattern_name,
                    "description": p.description,
                    "triggers": p.triggers,
                    "prevention_rule": p.prevention_rule,
                    "occurrence_count": p.occurrence_count,
                    "prevention_success_rate": p.prevention_success_rate,
                }
                for p in patterns
            ]
            
            # Load promotion wisdom (all skills, for cross-skill learning)
            # This helps us apply patterns that worked elsewhere
            summary = self.brain.summarize_for_skill(skill_name)
            if summary and "promotion_wisdom" in summary:
                context["promotion_wisdom"] = summary["promotion_wisdom"]
            
            # Load fixture library suggestions
            library = self.brain.fixture_library.entries
            if library:
                context["library_suggestions"] = [
                    {
                        "fixture_pattern_name": entry.fixture_pattern_name,
                        "description": entry.description,
                        "successful_skills": entry.successful_skills,
                        "anti_patterns": entry.anti_patterns,
                    }
                    for entry in library[:10]  # Top 10 suggestions
                ]
        except Exception as e:
            # Gracefully degrade if brain queries fail
            context["brain_load_error"] = str(e)
        
        return context
