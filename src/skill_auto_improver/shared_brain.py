"""
Shared brain for multi-skill orchestration.

Inspired by Claude's Subconscious pattern: structured memory blocks that:
- Capture insights across multiple skills
- Enable cross-skill learning (patterns from skill A inform skill B)
- Maintain coherent promotion wisdom and regression pattern library
- Provide a unified interface for skill orchestration

Memory blocks:
- core_directives: Fundamental rules for skill improvement across the system
- promotion_wisdom: Why certain patches got accepted (and across which fixtures)
- regression_patterns: Common failure modes with prevention strategies
- fixture_library: Shared fixture patterns and best practices
- skill_mastery: Per-skill insights (what works best for each skill type)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import re


@dataclass
class CoreDirective:
    """A single operational rule that applies across all skills."""
    id: str  # e.g. "cd_001_min_confidence"
    title: str
    description: str
    applies_to: list[str]  # skill patterns: ["weather*", "kiro*"], or ["*"] for all
    auto_apply: bool  # should this be enforced automatically?
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    example: Optional[str] = None

    def matches_skill(self, skill_name: str) -> bool:
        """Check if this directive applies to a given skill."""
        for pattern in self.applies_to:
            if pattern == "*":
                return True
            # Simple glob pattern matching
            import fnmatch
            if fnmatch.fnmatch(skill_name, pattern):
                return True
        return False


@dataclass
class PromotionWisdom:
    """Why a particular patch was accepted across skills."""
    id: str  # e.g. "pw_001_formal_greeting"
    fixture_name: str  # e.g. "formal_greeting_test"
    description: str
    acceptance_reason: str  # e.g. "100% recovery, zero regression, aligns with promotion baseline"
    skills_successful: list[str]  # which skills accepted this pattern
    proposal_type_sequence: list[str]  # the order/sequence that worked (e.g. ["test_case", "instruction"])
    confidence_floor: float  # e.g. 0.85
    confidence: float  # 0.8-1.0 across skills
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    promotion_count: int = 0  # how many times has this pattern been promoted?
    shared_lessons: list[str] = field(default_factory=list)  # reusable tips for other skills


@dataclass
class RegressionPattern:
    """A common failure mode observed across multiple skills."""
    id: str  # e.g. "rp_001_instruction_only_breaks_tests"
    pattern_name: str
    description: str
    triggers: list[str]  # e.g. ["instruction_proposal_without_test_case"]
    fix_strategy: str  # how to prevent/recover
    severity: str  # "warning" | "critical"
    observed_in_skills: list[str]  # which skills experienced this?
    prevention_rule: Optional[str]  # auto-apply this rule to prevent recurrence
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    occurrence_count: int = 1
    prevention_success_rate: float = 0.0  # % of times the prevention worked


@dataclass
class FixtureLibraryEntry:
    """Shared pattern for a fixture type that works well across skills."""
    id: str  # e.g. "fl_001_greeting_format"
    fixture_pattern_name: str
    description: str
    fixture_template: dict[str, Any]  # reusable fixture structure
    expected_behavior: str
    successful_skills: list[str]  # which skills use this successfully?
    anti_patterns: list[str]  # what breaks this fixture?
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    adaptability_notes: str = ""  # how to adapt this fixture for different skill types


@dataclass
class SkillMastery:
    """Learned insights specific to a skill type or individual skill."""
    skill_name: str
    skill_type: str = ""  # e.g. "weather", "kiro", "research"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    total_trials: int = 0
    successful_promotions: int = 0
    regression_incidents: int = 0
    average_proposal_confidence: float = 0.0
    most_effective_proposal_types: list[str] = field(default_factory=list)  # ["test_case", "instruction"]
    fixture_mastery: dict[str, dict[str, Any]] = field(default_factory=dict)  # per-fixture insights
    common_issues: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SharedBrain:
    """
    Multi-skill shared memory system.
    
    Maintains five structured memory blocks:
    1. core_directives: System-wide operational rules
    2. promotion_wisdom: Why patches succeeded (cross-skill)
    3. regression_patterns: Common failure modes and fixes
    4. fixture_library: Reusable fixture patterns
    5. skill_mastery: Per-skill learned insights
    """

    def __init__(self, brain_dir: Path | str):
        self.brain_dir = Path(brain_dir)
        self.brain_dir.mkdir(parents=True, exist_ok=True)

        # Define file paths for each memory block
        self.directives_path = self.brain_dir / "core_directives.json"
        self.promotion_wisdom_path = self.brain_dir / "promotion_wisdom.json"
        self.regression_patterns_path = self.brain_dir / "regression_patterns.json"
        self.fixture_library_path = self.brain_dir / "fixture_library.json"
        self.skill_mastery_path = self.brain_dir / "skill_mastery.json"

        # Load or initialize each block
        self.core_directives: dict[str, CoreDirective] = self._load_directives()
        self.promotion_wisdom: dict[str, PromotionWisdom] = self._load_promotion_wisdom()
        self.regression_patterns: dict[str, RegressionPattern] = self._load_regression_patterns()
        self.fixture_library: dict[str, FixtureLibraryEntry] = self._load_fixture_library()
        self.skill_mastery: dict[str, SkillMastery] = self._load_skill_mastery()

    def _load_directives(self) -> dict[str, CoreDirective]:
        """Load core directives from disk, or initialize with defaults."""
        if self.directives_path.exists():
            data = json.loads(self.directives_path.read_text())
            return {
                k: CoreDirective(**v) for k, v in data.items()
            }
        return self._init_default_directives()

    def _init_default_directives(self) -> dict[str, CoreDirective]:
        """Initialize core directives with sensible defaults."""
        directives = {
            "cd_001_min_confidence": CoreDirective(
                id="cd_001_min_confidence",
                title="Minimum Confidence Floor",
                description="Never auto-apply proposals below 0.80 confidence across any skill.",
                applies_to=["*"],
                auto_apply=True,
                example="Reject a 0.75-confidence instruction proposal; require manual review."
            ),
            "cd_002_test_case_first": CoreDirective(
                id="cd_002_test_case_first",
                title="Test Case Before Instruction",
                description="For any historically broken fixture, require a test_case proposal to accompany instruction proposals.",
                applies_to=["*"],
                auto_apply=True,
                example="Block instruction-only patches to a risky fixture; wait for regression test."
            ),
            "cd_003_no_churn": CoreDirective(
                id="cd_003_no_churn",
                title="Change Budget Enforcement",
                description="Reject patches that change >10 targets or add >100 lines without explicit approval.",
                applies_to=["*"],
                auto_apply=True,
                example="Rollback a patch that touched 15 files; review necessity before retry."
            ),
        }
        self._save_directives(directives)
        return directives

    def _load_promotion_wisdom(self) -> dict[str, PromotionWisdom]:
        """Load promotion wisdom from disk, or start empty."""
        if self.promotion_wisdom_path.exists():
            data = json.loads(self.promotion_wisdom_path.read_text())
            return {
                k: PromotionWisdom(**v) for k, v in data.items()
            }
        return {}

    def _load_regression_patterns(self) -> dict[str, RegressionPattern]:
        """Load regression patterns from disk, or start empty."""
        if self.regression_patterns_path.exists():
            data = json.loads(self.regression_patterns_path.read_text())
            return {
                k: RegressionPattern(**v) for k, v in data.items()
            }
        return {}

    def _load_fixture_library(self) -> dict[str, FixtureLibraryEntry]:
        """Load fixture library from disk, or start empty."""
        if self.fixture_library_path.exists():
            data = json.loads(self.fixture_library_path.read_text())
            return {
                k: FixtureLibraryEntry(**v) for k, v in data.items()
            }
        return {}

    def _load_skill_mastery(self) -> dict[str, SkillMastery]:
        """Load skill mastery from disk, or start empty."""
        if self.skill_mastery_path.exists():
            data = json.loads(self.skill_mastery_path.read_text())
            return {
                k: SkillMastery(**v) for k, v in data.items()
            }
        return {}

    # === Write methods ===

    def _save_directives(self, directives: dict[str, CoreDirective]) -> None:
        """Persist core directives."""
        data = {k: asdict(v) for k, v in directives.items()}
        self.directives_path.write_text(json.dumps(data, indent=2))

    def _save_promotion_wisdom(self, wisdom: dict[str, PromotionWisdom]) -> None:
        """Persist promotion wisdom."""
        data = {k: asdict(v) for k, v in wisdom.items()}
        self.promotion_wisdom_path.write_text(json.dumps(data, indent=2))

    def _save_regression_patterns(self, patterns: dict[str, RegressionPattern]) -> None:
        """Persist regression patterns."""
        data = {k: asdict(v) for k, v in patterns.items()}
        self.regression_patterns_path.write_text(json.dumps(data, indent=2))

    def _save_fixture_library(self, library: dict[str, FixtureLibraryEntry]) -> None:
        """Persist fixture library."""
        data = {k: asdict(v) for k, v in library.items()}
        self.fixture_library_path.write_text(json.dumps(data, indent=2))

    def _save_skill_mastery(self, mastery: dict[str, SkillMastery]) -> None:
        """Persist skill mastery."""
        data = {k: asdict(v) for k, v in mastery.items()}
        self.skill_mastery_path.write_text(json.dumps(data, indent=2))

    # === Query methods ===

    def get_directives_for_skill(self, skill_name: str) -> list[CoreDirective]:
        """Get all applicable directives for a skill."""
        return [d for d in self.core_directives.values() if d.matches_skill(skill_name)]

    def get_promotion_wisdom_for_fixture(self, fixture_name: str) -> list[PromotionWisdom]:
        """Find promotion wisdom entries that match a fixture pattern."""
        return [
            w for w in self.promotion_wisdom.values()
            if fixture_name.lower() in w.fixture_name.lower() or w.fixture_name.lower() in fixture_name.lower()
        ]

    def get_regression_patterns_for_skill(self, skill_name: str) -> list[RegressionPattern]:
        """Get regression patterns observed in a skill."""
        return [
            p for p in self.regression_patterns.values()
            if skill_name in p.observed_in_skills
        ]

    def get_similar_fixtures(self, fixture_name: str, limit: int = 5) -> list[FixtureLibraryEntry]:
        """Find similar fixtures in the library."""
        # Simple keyword matching for now
        keywords = set(re.split(r'_|[A-Z]', fixture_name.lower()))
        matches = []
        for entry in self.fixture_library.values():
            entry_keywords = set(re.split(r'_|[A-Z]', entry.fixture_pattern_name.lower()))
            overlap = len(keywords & entry_keywords)
            if overlap > 0:
                matches.append((overlap, entry))
        matches.sort(key=lambda x: -x[0])
        return [m[1] for m in matches[:limit]]

    def get_skill_mastery(self, skill_name: str) -> Optional[SkillMastery]:
        """Get learned insights for a specific skill."""
        return self.skill_mastery.get(skill_name)

    def get_or_create_skill_mastery(self, skill_name: str, skill_type: str = "") -> SkillMastery:
        """Get existing or create new skill mastery record."""
        if skill_name not in self.skill_mastery:
            self.skill_mastery[skill_name] = SkillMastery(skill_name=skill_name, skill_type=skill_type)
            self._save_skill_mastery(self.skill_mastery)
        return self.skill_mastery[skill_name]

    # === Update methods ===

    def record_promotion(
        self,
        fixture_name: str,
        skill_name: str,
        proposal_types: list[str],
        reason: str,
        confidence: float,
        shared_lessons: Optional[list[str]] = None,
    ) -> PromotionWisdom:
        """Record a successful promotion for cross-skill learning."""
        wisdom_id = f"pw_{len(self.promotion_wisdom):03d}_{fixture_name.lower()}"
        
        wisdom = PromotionWisdom(
            id=wisdom_id,
            fixture_name=fixture_name,
            description=f"Pattern accepted in {skill_name}",
            acceptance_reason=reason,
            skills_successful=[skill_name],
            proposal_type_sequence=proposal_types,
            confidence_floor=max(0.80, confidence - 0.05),
            confidence=confidence,
            shared_lessons=shared_lessons or [],
            promotion_count=1,
        )
        
        # Check for existing similar entry
        for existing_id, existing in self.promotion_wisdom.items():
            if existing.fixture_name == fixture_name:
                # Merge with existing
                if skill_name not in existing.skills_successful:
                    existing.skills_successful.append(skill_name)
                existing.promotion_count += 1
                existing.last_updated = datetime.now(timezone.utc).isoformat()
                self._save_promotion_wisdom(self.promotion_wisdom)
                return existing
        
        # New entry
        self.promotion_wisdom[wisdom_id] = wisdom
        self._save_promotion_wisdom(self.promotion_wisdom)
        return wisdom

    def record_regression(
        self,
        pattern_name: str,
        skill_name: str,
        trigger: str,
        fix_strategy: str,
        severity: str = "warning",
    ) -> RegressionPattern:
        """Record a regression pattern for system-wide awareness."""
        pattern_id = f"rp_{len(self.regression_patterns):03d}_{pattern_name.lower()}"
        
        # Check for existing
        for existing_id, existing in self.regression_patterns.items():
            if existing.pattern_name == pattern_name:
                if skill_name not in existing.observed_in_skills:
                    existing.observed_in_skills.append(skill_name)
                existing.occurrence_count += 1
                self._save_regression_patterns(self.regression_patterns)
                return existing
        
        pattern = RegressionPattern(
            id=pattern_id,
            pattern_name=pattern_name,
            description=f"Regression observed in {skill_name}: {trigger}",
            triggers=[trigger],
            fix_strategy=fix_strategy,
            severity=severity,
            observed_in_skills=[skill_name],
            prevention_rule=None,
            occurrence_count=1,
        )
        
        self.regression_patterns[pattern_id] = pattern
        self._save_regression_patterns(self.regression_patterns)
        return pattern

    def update_skill_mastery(self, skill_name: str, **updates) -> SkillMastery:
        """Update skill mastery with trial results."""
        mastery = self.get_or_create_skill_mastery(skill_name)
        
        for key, value in updates.items():
            if hasattr(mastery, key):
                if key == "fixture_mastery" and isinstance(value, dict):
                    # Merge fixture insights
                    mastery.fixture_mastery.update(value)
                elif key in ("most_effective_proposal_types", "common_issues"):
                    # Merge lists
                    existing = getattr(mastery, key, [])
                    for item in value:
                        if item not in existing:
                            existing.append(item)
                else:
                    setattr(mastery, key, value)
        
        mastery.last_updated = datetime.now(timezone.utc).isoformat()
        self._save_skill_mastery(self.skill_mastery)
        return mastery

    def add_fixture_to_library(
        self,
        fixture_pattern_name: str,
        fixture_template: dict[str, Any],
        expected_behavior: str,
        successful_skills: list[str],
    ) -> FixtureLibraryEntry:
        """Add a successful fixture pattern to the shared library."""
        entry_id = f"fl_{len(self.fixture_library):03d}_{fixture_pattern_name.lower()}"
        
        entry = FixtureLibraryEntry(
            id=entry_id,
            fixture_pattern_name=fixture_pattern_name,
            description=f"Fixture pattern successfully used in {', '.join(successful_skills)}",
            fixture_template=fixture_template,
            expected_behavior=expected_behavior,
            successful_skills=successful_skills,
            anti_patterns=[],
        )
        
        self.fixture_library[entry_id] = entry
        self._save_fixture_library(self.fixture_library)
        return entry

    def summarize_for_skill(self, skill_name: str) -> dict[str, Any]:
        """Generate a summary of all shared brain insights relevant to a skill."""
        mastery = self.get_skill_mastery(skill_name)
        directives = self.get_directives_for_skill(skill_name)
        
        return {
            "skill_name": skill_name,
            "mastery": asdict(mastery) if mastery else None,
            "applicable_directives": [asdict(d) for d in directives],
            "active_regression_patterns": [
                asdict(p) for p in self.get_regression_patterns_for_skill(skill_name)
            ],
            "total_promotions_across_system": len(self.promotion_wisdom),
            "total_regression_incidents": sum(p.occurrence_count for p in self.regression_patterns.values()),
        }
