"""
Automated promotion rules engine.

Learns from past successful proposals and applies acceptance rules automatically
to new proposals, skipping operator review for low-risk, high-confidence cases.

Key ideas:
- Brain stores successful proposal patterns (PromotionWisdom)
- Each pattern includes: fixture name, proposal type sequence, confidence, skills where it worked
- When a new proposal arrives, check if it matches a learned pattern
- If match + confidence high enough, auto-apply (skip review)
- If no match or low confidence, escalate to operator

Rules can be:
- Pattern-based: "If test_case proposal for fixture X on skill Y, auto-accept"
- Sequence-based: "If instruction→test_case sequence on regression-prone fixture, review first"
- Cross-skill: "If pattern successful in N skills, confidence ≥ 0.9, auto-apply elsewhere"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any
import json
from pathlib import Path

from .shared_brain import PromotionWisdom
from .proposer import PatchProposal


@dataclass
class PromotionRule:
    """A rule that can be applied to auto-accept or escalate proposals."""
    id: str
    name: str
    description: str
    
    # Matching criteria
    fixture_pattern: Optional[str] = None  # glob pattern, e.g. "auth*", or exact match
    proposal_type: Optional[str] = None  # "instruction" | "test_case" | "artifact" | None (any)
    min_confidence: float = 0.85  # 0-1.0
    min_cross_skill_adoption: int = 1  # "has this pattern worked in N+ skills?"
    
    # Decision
    auto_apply: bool = True  # if True, skip operator review
    escalation_reason: Optional[str] = None  # if False, why escalate?
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    enabled: bool = True
    source_wisdom_id: Optional[str] = None  # which PromotionWisdom learned this?
    
    def matches(self, proposal: PatchProposal, promotion_wisdom: PromotionWisdom) -> bool:
        """Check if this rule applies to a given proposal and wisdom."""
        # Check fixture pattern
        if self.fixture_pattern:
            import fnmatch
            if not fnmatch.fnmatch(promotion_wisdom.fixture_name, self.fixture_pattern):
                return False
        
        # Check proposal type
        if self.proposal_type and proposal.type != self.proposal_type:
            return False
        
        # Check confidence
        if promotion_wisdom.confidence < self.min_confidence:
            return False
        
        # Check cross-skill adoption
        if len(promotion_wisdom.skills_successful) < self.min_cross_skill_adoption:
            return False
        
        return True


@dataclass
class PromotionRulesDecision:
    """Decision output from the promotion rules engine."""
    should_auto_apply: bool
    rule_matched: Optional[PromotionRule] = None
    confidence: float = 0.0
    reasoning: str = ""
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    matched_wisdom: Optional[PromotionWisdom] = None


class PromotionRulesEngine:
    """
    Learns from successful proposals and applies acceptance rules automatically.
    """
    
    def __init__(self, brain_path: Path | str):
        self.brain_path = Path(brain_path)
        self.rules_file = self.brain_path / "promotion_rules.json"
        self.rules = self._load_rules()
    
    def _load_rules(self) -> list[PromotionRule]:
        """Load promotion rules from disk."""
        if not self.rules_file.exists():
            return []
        
        with open(self.rules_file) as f:
            data = json.load(f)
        
        return [
            PromotionRule(**rule) for rule in data.get("rules", [])
        ]
    
    def _save_rules(self):
        """Persist rules to disk."""
        data = {
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "fixture_pattern": r.fixture_pattern,
                    "proposal_type": r.proposal_type,
                    "min_confidence": r.min_confidence,
                    "min_cross_skill_adoption": r.min_cross_skill_adoption,
                    "auto_apply": r.auto_apply,
                    "escalation_reason": r.escalation_reason,
                    "created_at": r.created_at,
                    "last_updated": r.last_updated,
                    "enabled": r.enabled,
                    "source_wisdom_id": r.source_wisdom_id,
                }
                for r in self.rules
            ],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rules_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def learn_from_promotion(self, wisdom: PromotionWisdom) -> None:
        """
        Learn a new rule from a successful promotion.
        
        If a PromotionWisdom has high confidence and cross-skill adoption,
        create or update a rule to auto-apply similar proposals in the future.
        """
        # Thresholds for auto-creating rules
        if wisdom.confidence < 0.85 or len(wisdom.skills_successful) < 2:
            # Not confident enough to auto-apply across skills
            return
        
        # Create a rule from this wisdom
        rule_id = f"rule_{wisdom.id}"
        existing = next((r for r in self.rules if r.source_wisdom_id == wisdom.id), None)
        
        if existing:
            # Update existing rule
            existing.enabled = True
            existing.last_updated = datetime.now(timezone.utc).isoformat()
        else:
            # Create new rule
            rule = PromotionRule(
                id=rule_id,
                name=f"Auto-apply: {wisdom.fixture_name}",
                description=f"Pattern learned from {len(wisdom.skills_successful)} successful skills: {', '.join(wisdom.skills_successful[:3])}",
                fixture_pattern=wisdom.fixture_name,
                proposal_type=wisdom.proposal_type_sequence[0] if wisdom.proposal_type_sequence else None,
                min_confidence=wisdom.confidence - 0.05,  # slightly looser threshold
                min_cross_skill_adoption=len(wisdom.skills_successful),
                auto_apply=True,
                source_wisdom_id=wisdom.id,
            )
            self.rules.append(rule)
        
        self._save_rules()
    
    def evaluate_proposal(
        self,
        proposal: PatchProposal,
        skill_name: str,
        promotion_wisdom_list: list[PromotionWisdom],
    ) -> PromotionRulesDecision:
        """
        Evaluate whether a proposal should auto-apply or escalate.
        
        Returns a decision with reasoning.
        """
        enabled_rules = [r for r in self.rules if r.enabled]
        
        if not enabled_rules:
            return PromotionRulesDecision(
                should_auto_apply=False,
                escalation_required=True,
                escalation_reason="No promotion rules configured; escalate for operator review",
                reasoning="No learned patterns yet",
            )
        
        # Try to find matching wisdom for this proposal
        matched_wisdom = None
        for wisdom in promotion_wisdom_list:
            # Check if this wisdom matches the proposal's fixture intent
            # (This is a simplified check; in practice you'd compare proposal.hotspot_fixture_name)
            if proposal.fixture_name and proposal.fixture_name in wisdom.fixture_name:
                matched_wisdom = wisdom
                break
        
        if not matched_wisdom:
            return PromotionRulesDecision(
                should_auto_apply=False,
                escalation_required=True,
                escalation_reason=f"No learned pattern for fixture '{proposal.fixture_name}'; escalate for review",
                reasoning="Proposal doesn't match any learned wisdom",
            )
        
        # Check if any rule matches
        for rule in enabled_rules:
            if rule.matches(proposal, matched_wisdom):
                return PromotionRulesDecision(
                    should_auto_apply=rule.auto_apply,
                    rule_matched=rule,
                    confidence=matched_wisdom.confidence,
                    reasoning=f"Matched rule '{rule.name}' with {matched_wisdom.confidence:.1%} confidence",
                    matched_wisdom=matched_wisdom,
                )
        
        # No rule matched, but we have high-confidence wisdom
        if matched_wisdom.confidence >= 0.90:
            return PromotionRulesDecision(
                should_auto_apply=True,
                confidence=matched_wisdom.confidence,
                reasoning=f"High-confidence wisdom ({matched_wisdom.confidence:.1%}) with no conflicting rules",
                matched_wisdom=matched_wisdom,
            )
        
        # Default: escalate
        return PromotionRulesDecision(
            should_auto_apply=False,
            escalation_required=True,
            escalation_reason="Matched wisdom confidence below threshold; escalate for review",
            reasoning=f"Confidence {matched_wisdom.confidence:.1%} below escalation floor",
        )
    
    def get_stats(self) -> dict[str, Any]:
        """Return stats about the rules engine."""
        enabled = [r for r in self.rules if r.enabled]
        return {
            "total_rules": len(self.rules),
            "enabled_rules": len(enabled),
            "by_proposal_type": {
                t: len([r for r in enabled if r.proposal_type == t or r.proposal_type is None])
                for t in ["instruction", "test_case", "artifact"]
            },
            "avg_min_confidence": sum(r.min_confidence for r in enabled) / len(enabled) if enabled else 0,
        }

    def summarize_dashboard(self, *, limit: int = 5) -> dict[str, Any]:
        """Return an operator-facing summary of learned promotion rules."""
        enabled = [r for r in self.rules if r.enabled]
        disabled = [r for r in self.rules if not r.enabled]
        top_auto_apply = sorted(
            [r for r in enabled if r.auto_apply],
            key=lambda item: (-item.min_cross_skill_adoption, -item.min_confidence, item.name),
        )[:limit]
        top_escalation = sorted(
            [r for r in enabled if not r.auto_apply],
            key=lambda item: (-item.min_cross_skill_adoption, -item.min_confidence, item.name),
        )[:limit]

        return {
            "counts": {
                "total": len(self.rules),
                "enabled": len(enabled),
                "disabled": len(disabled),
                "auto_apply": len([r for r in enabled if r.auto_apply]),
                "escalation": len([r for r in enabled if not r.auto_apply]),
            },
            "stats": self.get_stats(),
            "top_auto_apply_rules": [self._rule_to_dict(rule) for rule in top_auto_apply],
            "top_escalation_rules": [self._rule_to_dict(rule) for rule in top_escalation],
        }

    @staticmethod
    def _rule_to_dict(rule: PromotionRule) -> dict[str, Any]:
        return {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "fixture_pattern": rule.fixture_pattern,
            "proposal_type": rule.proposal_type,
            "min_confidence": rule.min_confidence,
            "min_cross_skill_adoption": rule.min_cross_skill_adoption,
            "auto_apply": rule.auto_apply,
            "escalation_reason": rule.escalation_reason,
            "enabled": rule.enabled,
            "source_wisdom_id": rule.source_wisdom_id,
            "created_at": rule.created_at,
            "last_updated": rule.last_updated,
        }
