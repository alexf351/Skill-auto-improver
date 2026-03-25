"""
Memory-Driven Proposal Ranking

Reorders proposals based on per-fixture success history, acceptance patterns,
and learned fixture similarities from operating memory.

Patterns tracked:
- Which proposal types succeed for which fixtures
- Fixture resolution time (fixtures resolved quickly vs slowly)
- Cross-fixture resolution patterns (similar fixtures guide each other)
- Acceptance/rejection history (which proposals are accepted vs blocked)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
from datetime import datetime, timedelta


@dataclass(slots=True)
class FixtureSuccessRecord:
    """Success history for a single fixture."""
    fixture_name: str
    total_attempts: int = 0
    successful_attempts: int = 0
    accepted_proposal_types: dict[str, int] = field(default_factory=dict)  # type -> count
    rejected_proposal_types: dict[str, int] = field(default_factory=dict)  # type -> count
    last_success_time: str | None = None  # ISO timestamp
    last_attempt_time: str | None = None  # ISO timestamp
    avg_attempts_to_success: float = 0.0  # rolling avg
    preferred_proposal_types: list[str] = field(default_factory=list)  # ordered by success rate

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.5  # neutral default
        return self.successful_attempts / self.total_attempts

    @property
    def is_historically_difficult(self) -> bool:
        """Fixture that takes many attempts to fix."""
        return self.avg_attempts_to_success >= 2.0 or (self.total_attempts > 3 and self.success_rate < 0.5)

    def get_acceptance_rate(self, proposal_type: str) -> float:
        """How often does this proposal type succeed for this fixture?"""
        accepted = self.accepted_proposal_types.get(proposal_type, 0)
        rejected = self.rejected_proposal_types.get(proposal_type, 0)
        total = accepted + rejected
        if total == 0:
            return 0.5  # neutral if no history
        return accepted / total

    def record_acceptance(self, proposal_type: str) -> None:
        """Record that a proposal of this type was accepted."""
        self.accepted_proposal_types[proposal_type] = self.accepted_proposal_types.get(proposal_type, 0) + 1
        self.total_attempts += 1
        self.successful_attempts += 1
        self._update_preferred_types()
        self._recalc_avg_attempts()
        self.last_success_time = datetime.utcnow().isoformat()
        self.last_attempt_time = datetime.utcnow().isoformat()

    def record_rejection(self, proposal_type: str) -> None:
        """Record that a proposal of this type was rejected."""
        self.rejected_proposal_types[proposal_type] = self.rejected_proposal_types.get(proposal_type, 0) + 1
        self.total_attempts += 1
        self._update_preferred_types()
        self._recalc_avg_attempts()
        self.last_attempt_time = datetime.utcnow().isoformat()

    def _update_preferred_types(self) -> None:
        """Reorder preferred types by acceptance rate."""
        all_types = set(self.accepted_proposal_types.keys()) | set(self.rejected_proposal_types.keys())
        self.preferred_proposal_types = sorted(
            all_types,
            key=lambda t: self.get_acceptance_rate(t),
            reverse=True,
        )

    def _recalc_avg_attempts(self) -> None:
        """Recalculate rolling average attempts to success."""
        if self.successful_attempts == 0:
            self.avg_attempts_to_success = 0.0
        else:
            self.avg_attempts_to_success = self.total_attempts / self.successful_attempts

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            "fixture_name": self.fixture_name,
            "total_attempts": self.total_attempts,
            "successful_attempts": self.successful_attempts,
            "success_rate": self.success_rate,
            "accepted_proposal_types": self.accepted_proposal_types,
            "rejected_proposal_types": self.rejected_proposal_types,
            "last_success_time": self.last_success_time,
            "last_attempt_time": self.last_attempt_time,
            "avg_attempts_to_success": self.avg_attempts_to_success,
            "preferred_proposal_types": self.preferred_proposal_types,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> FixtureSuccessRecord:
        """Deserialize from JSON dict."""
        return FixtureSuccessRecord(
            fixture_name=data["fixture_name"],
            total_attempts=data.get("total_attempts", 0),
            successful_attempts=data.get("successful_attempts", 0),
            accepted_proposal_types=data.get("accepted_proposal_types", {}),
            rejected_proposal_types=data.get("rejected_proposal_types", {}),
            last_success_time=data.get("last_success_time"),
            last_attempt_time=data.get("last_attempt_time"),
            avg_attempts_to_success=data.get("avg_attempts_to_success", 0.0),
            preferred_proposal_types=data.get("preferred_proposal_types", []),
        )


@dataclass(slots=True)
class FixtureSimilarity:
    """Similarity score between two fixtures."""
    fixture_a: str
    fixture_b: str
    similarity_score: float  # 0.0-1.0, based on name/tag overlap
    shared_traits: list[str] = field(default_factory=list)

    def __lt__(self, other: FixtureSimilarity) -> bool:
        """Standard ascending comparison for sorting."""
        return self.similarity_score < other.similarity_score


class MemoryDrivenRanker:
    """
    Reorders proposals based on fixture success history.

    Reads from operating memory to build success records per fixture,
    then uses those to guide proposal ordering:
    - Prioritize proposal types that succeed for this fixture
    - De-prioritize types that have been rejected before
    - Use fixture similarity to borrow success patterns from similar fixtures
    - Time-decay: recent successes weight more heavily
    """

    def __init__(self, memory_dir: str | Path | None = None):
        """
        Initialize ranker with optional memory directory.

        Args:
            memory_dir: Path to skill operating memory root.
                       If provided, loads success records from data/fixture-success.jsonl
        """
        self.memory_dir = Path(memory_dir) if memory_dir else None
        self.success_records: dict[str, FixtureSuccessRecord] = {}
        self._load_success_records()

    def _load_success_records(self) -> None:
        """Load success records from disk if available."""
        if not self.memory_dir:
            return

        records_path = self.memory_dir / "data" / "fixture-success.jsonl"
        if not records_path.exists():
            return

        try:
            with open(records_path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    record = FixtureSuccessRecord.from_dict(data)
                    self.success_records[record.fixture_name] = record
        except Exception:
            # Graceful degradation: if loading fails, start fresh
            pass

    def record_proposal_outcome(
        self,
        fixture_name: str,
        proposal_type: str,
        accepted: bool,
    ) -> None:
        """
        Record that a proposal was accepted or rejected.

        Args:
            fixture_name: Name of the fixture
            proposal_type: Type of proposal (instruction, test_case, etc.)
            accepted: Whether the proposal was accepted
        """
        if fixture_name not in self.success_records:
            self.success_records[fixture_name] = FixtureSuccessRecord(fixture_name=fixture_name)

        record = self.success_records[fixture_name]
        if accepted:
            record.record_acceptance(proposal_type)
        else:
            record.record_rejection(proposal_type)

    def rank_proposals(self, proposals: list[Any], fixture_name: str) -> list[tuple[Any, float]]:
        """
        Reorder proposals for a specific fixture based on success history.

        Args:
            proposals: List of proposals (must have .type and .fixture_name attributes)
            fixture_name: Fixture name to rank for

        Returns:
            List of (proposal, rank_score) tuples, sorted by rank_score descending
        """
        record = self.success_records.get(fixture_name) or FixtureSuccessRecord(fixture_name=fixture_name)
        similar_fixtures = self._find_similar_fixtures(fixture_name)

        ranked = []
        for proposal in proposals:
            if proposal.fixture_name != fixture_name:
                continue

            score = self._compute_rank_score(proposal, record, similar_fixtures)
            ranked.append((proposal, score))

        # Sort by score descending
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _compute_rank_score(
        self,
        proposal: Any,
        record: FixtureSuccessRecord,
        similar_fixtures: list[FixtureSimilarity],
    ) -> float:
        """
        Compute a ranking score for a single proposal.

        Score considers:
        - Direct acceptance rate for this fixture + type
        - Recency bonus (recent successes weight more)
        - Difficulty adjustment (hard fixtures prioritize reliable types)
        - Similarity borrowing (similar fixtures' success guides this one)

        Args:
            proposal: Proposal with .type attribute
            record: Success record for this fixture
            similar_fixtures: List of similar fixtures

        Returns:
            Score 0.0-1.0+ (can exceed 1.0 with bonuses)
        """
        proposal_type = proposal.type

        # Base: direct acceptance rate for this type on this fixture
        direct_rate = record.get_acceptance_rate(proposal_type)
        score = direct_rate

        # Recency bonus: recent successes weight more
        if record.last_success_time:
            time_delta = datetime.utcnow() - datetime.fromisoformat(record.last_success_time)
            # Full bonus if <24h, decays over 7 days
            days_since = max(0, time_delta.days)
            recency_bonus = max(0.0, 0.1 * (1.0 - (days_since / 7.0)))
            score += recency_bonus

        # Difficulty adjustment: hard fixtures prioritize reliable types
        if record.is_historically_difficult:
            # Boost high-confidence types, slight penalty for low-confidence
            if record.get_acceptance_rate(proposal_type) > 0.7:
                score += 0.15
            elif record.get_acceptance_rate(proposal_type) < 0.3:
                score -= 0.1

        # Similarity borrowing: check similar fixtures' success with this type
        borrowed_scores = []
        for sim in similar_fixtures[:3]:  # Top 3 most similar
            other_record = self.success_records.get(sim.fixture_b)
            if other_record:
                other_rate = other_record.get_acceptance_rate(proposal_type)
                # Weight by similarity
                borrowed_scores.append(other_rate * (sim.similarity_score * 0.5))

        if borrowed_scores:
            avg_borrowed = sum(borrowed_scores) / len(borrowed_scores)
            score += avg_borrowed

        return min(score, 1.99)  # Cap at ~2.0 for stable sorting

    def _find_similar_fixtures(self, fixture_name: str) -> list[FixtureSimilarity]:
        """
        Find similar fixtures by name/tag overlap.

        Simple heuristic: extract base name (before _), find fixtures sharing that base.
        Example: "api_get" -> similar to "api_post", "api_delete" etc.

        Args:
            fixture_name: Target fixture name

        Returns:
            List of FixtureSimilarity, sorted by score descending
        """
        parts = fixture_name.split("_")
        base = parts[0] if parts else ""

        similarities = []
        for other_name in self.success_records.keys():
            if other_name == fixture_name:
                continue

            other_parts = other_name.split("_")
            other_base = other_parts[0] if other_parts else ""

            # Simple similarity: shared base name + partial overlap
            shared_traits = []
            similarity = 0.0

            if base and other_base == base:
                shared_traits.append("shared_base")
                similarity += 0.4

            # Tag overlap (if any fixtures have tags in memory)
            if len(parts) > 1 and len(other_parts) > 1:
                shared_tags = set(parts[1:]) & set(other_parts[1:])
                if shared_tags:
                    shared_traits.extend(list(shared_tags))
                    similarity += 0.3 * (len(shared_tags) / max(len(parts) - 1, len(other_parts) - 1))

            if similarity > 0.0:
                similarities.append(
                    FixtureSimilarity(
                        fixture_a=fixture_name,
                        fixture_b=other_name,
                        similarity_score=similarity,
                        shared_traits=shared_traits,
                    )
                )

        similarities.sort(reverse=True)  # Sorted by score descending
        return similarities

    def save_success_records(self, memory_dir: str | Path | None = None) -> None:
        """
        Persist success records to disk for next session.

        Args:
            memory_dir: Path to save to. If None, uses self.memory_dir.
        """
        target_dir = Path(memory_dir or self.memory_dir or ".")
        records_path = target_dir / "data" / "fixture-success.jsonl"

        records_path.parent.mkdir(parents=True, exist_ok=True)

        with open(records_path, "w") as f:
            for record in self.success_records.values():
                f.write(json.dumps(record.to_dict()) + "\n")

    def summary(self) -> dict[str, Any]:
        """Return a summary of success statistics."""
        if not self.success_records:
            return {
                "total_fixtures": 0,
                "fixtures_tracked": [],
                "avg_success_rate": 0.0,
                "historically_difficult": [],
            }

        difficult = [r for r in self.success_records.values() if r.is_historically_difficult]
        avg_rate = (
            sum(r.success_rate for r in self.success_records.values()) / len(self.success_records)
            if self.success_records
            else 0.0
        )

        return {
            "total_fixtures": len(self.success_records),
            "fixtures_tracked": list(self.success_records.keys()),
            "avg_success_rate": round(avg_rate, 3),
            "historically_difficult": [r.fixture_name for r in difficult],
            "fixture_details": {
                name: record.to_dict() for name, record in self.success_records.items()
            },
        }
