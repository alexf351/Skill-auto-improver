from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DOCTRINE = """# doctrine.md

## Plan Node Default
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, stop and re-plan immediately
- Use plan mode for verification too, not just building
- Write detailed specs up front to reduce ambiguity

## Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis
- One task per subagent for focused execution

## Verification Before Done
- Never mark a task complete without proving it works
- Run tests, inspect logs, and demonstrate correctness
- Ask: would a staff engineer approve this?

## Demand Elegance (Balanced)
- For non-trivial changes, ask if there is a more elegant solution
- Avoid over-engineering simple fixes
- Challenge your own work before presenting it

## Autonomous Bug Fixing
- When given a bug, fix it without forcing user hand-holding
- Point at logs, errors, failing tests, then resolve them

## Core Principles
- Simplicity first
- No laziness
- Root cause over temporary patches
"""

DEFAULT_LESSONS = """# lessons.md

Capture reusable corrections here.

## Format
- Date:
- Pattern:
- Rule:
- Example:

## Entries
"""

DEFAULT_TODO = """# todo.md

## Plan
- [ ] Define task
- [ ] Break into checkable items
- [ ] Verify approach before implementation

## Progress
- [ ] In progress

## Review
- Results:
- Verification:
- Follow-ups:
"""

DEFAULT_GOTCHAS = """# gotchas.md

Record repeated failure modes and anti-patterns.

## Format
- Failure:
- Trigger:
- Prevention:

## Gotchas
"""

DEFAULT_VERIFICATION = """# verification.md

## Verification Standard
- Never claim done without proof
- Run tests where available
- Check logs / actual outputs
- State what was not tested

## Proof block template
- Attempted:
- Verified by:
- Actual live state:
- Confidence:
"""

DEFAULT_PREFERENCES = {
    "style": [],
    "format": [],
    "tooling": [],
    "verification": [],
    "proposal": {
        "boost_terms": [],
        "avoid_terms": [],
        "prefer_types": [],
        "min_confidence": None,
        "accepted_severities": [],
        "rollback_on_regression": True,
        "require_recovery_for_accept": False,
        "protect_promoted_fixtures": True,
        "promotion_history_window": 5,
        "min_promotions_for_fixture_guard": 2,
        "rollback_on_history_regression": True,
        "require_test_case_for_protected_fixtures": False,
        "max_changed_targets": None,
        "max_added_lines": None,
        "fixture_policies": {},
    },
}

FILES = {
    "doctrine.md": DEFAULT_DOCTRINE,
    "lessons.md": DEFAULT_LESSONS,
    "todo.md": DEFAULT_TODO,
    "gotchas.md": DEFAULT_GOTCHAS,
    "verification.md": DEFAULT_VERIFICATION,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def scaffold_operating_memory(skill_path: str | Path, force: bool = False) -> dict[str, Any]:
    root = Path(skill_path)
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []

    for name, content in FILES.items():
        target = root / name
        if target.exists() and not force:
            skipped.append(name)
            continue
        target.write_text(content, encoding="utf-8")
        created.append(name)

    pref = data_dir / "preferences.json"
    if pref.exists() and not force:
        skipped.append("data/preferences.json")
    else:
        pref.write_text(json.dumps(DEFAULT_PREFERENCES, indent=2), encoding="utf-8")
        created.append("data/preferences.json")

    history = data_dir / "run-history.jsonl"
    if history.exists() and not force:
        skipped.append("data/run-history.jsonl")
    else:
        history.write_text("", encoding="utf-8")
        created.append("data/run-history.jsonl")

    feedback = data_dir / "feedback.log"
    if feedback.exists() and not force:
        skipped.append("data/feedback.log")
    else:
        feedback.write_text("", encoding="utf-8")
        created.append("data/feedback.log")

    promotion = data_dir / "promotion.json"
    if promotion.exists() and not force:
        skipped.append("data/promotion.json")
    else:
        promotion.write_text(json.dumps({"current": None, "history": []}, indent=2), encoding="utf-8")
        created.append("data/promotion.json")

    return {
        "skill_path": str(root),
        "created": created,
        "skipped": skipped,
    }


class OperatingMemory:
    def __init__(self, skill_path: str | Path):
        self.root = Path(skill_path)
        self.data_dir = self.root / "data"
        self.todo_path = self.root / "todo.md"
        self.lessons_path = self.root / "lessons.md"
        self.gotchas_path = self.root / "gotchas.md"
        self.verification_path = self.root / "verification.md"
        self.doctrine_path = self.root / "doctrine.md"
        self.preferences_path = self.data_dir / "preferences.json"
        self.history_path = self.data_dir / "run-history.jsonl"
        self.promotion_path = self.data_dir / "promotion.json"

    def ensure(self) -> dict[str, Any]:
        return scaffold_operating_memory(self.root)

    def load_context(self) -> dict[str, Any]:
        self.ensure()
        preferences = self._load_preferences()
        proposal_preferences = preferences.get("proposal", {}) if isinstance(preferences, dict) else {}

        history_entries = self._read_history_entries(limit=25)
        recent_history = history_entries[-5:]
        promotion_state = self._load_promotion_state()
        lesson_lines = self._extract_bullets(self.lessons_path)
        gotcha_lines = self._extract_bullets(self.gotchas_path)
        doctrine_lines = self._extract_bullets(self.doctrine_path)
        lesson_entries = self._parse_structured_entries(self.lessons_path, first_key="Pattern")
        gotcha_entries = self._parse_structured_entries(self.gotchas_path, first_key="Failure")
        fixture_profiles = self._build_fixture_profiles(
            lesson_entries=lesson_entries,
            gotcha_entries=gotcha_entries,
            history_entries=history_entries,
            proposal_preferences=proposal_preferences,
        )

        promotion_profiles = self._build_promotion_profiles(
            promotion_state=promotion_state,
            history_entries=history_entries,
            proposal_preferences=proposal_preferences,
        )
        boosted_fixtures = sorted(
            {
                fixture_name
                for fixture_name, profile in fixture_profiles.items()
                if profile.get("regression_prone") or profile.get("recovered_before")
            }
            | {
                fixture_name
                for fixture_name, profile in promotion_profiles.items()
                if profile.get("historically_protected")
            }
        )

        return {
            "doctrine": doctrine_lines,
            "lessons": lesson_lines,
            "gotchas": gotcha_lines,
            "preferences": preferences,
            "history": {
                "recent": recent_history,
                "accepted_count": sum(1 for entry in history_entries if entry.get("accepted")),
                "rollback_count": sum(1 for entry in history_entries if entry.get("rolled_back")),
                "regression_count": sum(entry.get("regressed_count", 0) for entry in history_entries),
                "recovery_count": sum(entry.get("recovered_count", 0) for entry in history_entries),
                "fixture_stats": {
                    fixture_name: profile["history"]
                    for fixture_name, profile in fixture_profiles.items()
                    if profile.get("history")
                },
            },
            "structured_memory": {
                "lessons": lesson_entries,
                "gotchas": gotcha_entries,
            },
            "proposal_hints": {
                "boost_terms": proposal_preferences.get("boost_terms", []),
                "avoid_terms": proposal_preferences.get("avoid_terms", []),
                "prefer_types": proposal_preferences.get("prefer_types", []),
                "boosted_fixtures": boosted_fixtures,
                "fixture_profiles": fixture_profiles,
                "promotion_profiles": promotion_profiles,
            },
            "policy": {
                "min_confidence": proposal_preferences.get("min_confidence"),
                "accepted_severities": proposal_preferences.get("accepted_severities", []),
                "rollback_on_regression": proposal_preferences.get("rollback_on_regression", True),
                "require_recovery_for_accept": proposal_preferences.get("require_recovery_for_accept", False),
                "protect_promoted_fixtures": proposal_preferences.get("protect_promoted_fixtures", True),
                "promotion_history_window": proposal_preferences.get("promotion_history_window", 5),
                "min_promotions_for_fixture_guard": proposal_preferences.get("min_promotions_for_fixture_guard", 2),
                "rollback_on_history_regression": proposal_preferences.get("rollback_on_history_regression", True),
                "require_test_case_for_protected_fixtures": proposal_preferences.get("require_test_case_for_protected_fixtures", False),
                "max_changed_targets": proposal_preferences.get("max_changed_targets"),
                "max_added_lines": proposal_preferences.get("max_added_lines"),
                "fixture_policies": proposal_preferences.get("fixture_policies", {}),
            },
        }

    def merge_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        memory_policy = self.load_context().get("policy", {})
        merged = dict(policy)
        if merged.get("min_confidence") in (None, 0, 0.0) and memory_policy.get("min_confidence") not in (None, ""):
            merged["min_confidence"] = memory_policy["min_confidence"]
        if not merged.get("accepted_severities") and memory_policy.get("accepted_severities"):
            merged["accepted_severities"] = memory_policy["accepted_severities"]
        if "rollback_on_regression" not in merged:
            merged["rollback_on_regression"] = memory_policy.get("rollback_on_regression", True)
        merged.setdefault("require_recovery_for_accept", memory_policy.get("require_recovery_for_accept", False))
        merged.setdefault("protect_promoted_fixtures", memory_policy.get("protect_promoted_fixtures", True))
        merged.setdefault("promotion_history_window", memory_policy.get("promotion_history_window", 5))
        merged.setdefault("min_promotions_for_fixture_guard", memory_policy.get("min_promotions_for_fixture_guard", 2))
        merged.setdefault("rollback_on_history_regression", memory_policy.get("rollback_on_history_regression", True))
        merged.setdefault("require_test_case_for_protected_fixtures", memory_policy.get("require_test_case_for_protected_fixtures", False))
        if merged.get("max_changed_targets") in (None, "") and memory_policy.get("max_changed_targets") not in (None, ""):
            merged["max_changed_targets"] = memory_policy.get("max_changed_targets")
        if merged.get("max_added_lines") in (None, "") and memory_policy.get("max_added_lines") not in (None, ""):
            merged["max_added_lines"] = memory_policy.get("max_added_lines")
        merged.setdefault("fixture_policies", memory_policy.get("fixture_policies", {}))
        return merged

    def record_trial(
        self,
        *,
        result: dict[str, Any],
        proposals: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        scaffold_result = self.ensure()
        timestamp = _utc_now()
        apply = result.get("apply", {})
        ab = result.get("ab", {})

        entry = {
            "timestamp": timestamp,
            "kind": "safe_patch_trial",
            "skill_path": str(self.root),
            "accepted": result.get("accepted", False),
            "rolled_back": result.get("rolled_back", False),
            "rollback_count": result.get("rollback_count", 0),
            "applied_count": apply.get("applied_count", 0),
            "skipped_count": apply.get("skipped_count", 0),
            "proposal_count": len(proposals),
            "proposal_types": sorted({proposal.get("type", "") for proposal in proposals if proposal.get("type")}),
            "fixture_names": sorted({proposal.get("fixture_name", "") for proposal in proposals if proposal.get("fixture_name")}),
            "pass_rate_delta": ab.get("pass_rate_delta", 0.0),
            "recovered_count": ab.get("recovered_count", 0),
            "regressed_count": ab.get("regressed_count", 0),
            "policy": policy,
        }
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

        summary = self._build_summary(entry)
        self._append_section(self.todo_path, "Review", summary["todo"])
        self._append_section(self.verification_path, "Proof block template", summary["verification"])

        if entry["accepted"] and entry["recovered_count"] > 0:
            self._append_section(self.lessons_path, "Entries", summary["lesson"])

        if entry["rolled_back"] or entry["regressed_count"] > 0:
            self._append_section(self.gotchas_path, "Gotchas", summary["gotcha"])

        promotion = self.update_promotion_state(result=result)

        return {
            "scaffold": scaffold_result,
            "history_path": str(self.history_path),
            "entry": entry,
            "promotion": promotion,
            "updated": [
                str(self.todo_path),
                str(self.verification_path),
                str(self.lessons_path) if entry["accepted"] and entry["recovered_count"] > 0 else None,
                str(self.gotchas_path) if entry["rolled_back"] or entry["regressed_count"] > 0 else None,
                promotion.get("promotion_path"),
            ],
            "context": self.load_context(),
        }

    def summarize_backups(self) -> dict[str, Any]:
        backups_dir = self.root / ".skill-auto-improver" / "backups"
        backups = sorted(backups_dir.glob("*.bak"), reverse=True)
        per_target: dict[str, int] = {}
        latest_by_target: dict[str, str] = {}
        for backup in backups:
            parts = backup.name.split(".")
            if len(parts) < 4:
                continue
            created_at = parts[-2]
            target = ".".join(parts[:-2])
            per_target[target] = per_target.get(target, 0) + 1
            latest_by_target.setdefault(target, created_at)
        return {
            "total_backups": len(backups),
            "targets": per_target,
            "latest_backup_ids": latest_by_target,
        }

    def evaluate_promotion_guard(
        self,
        *,
        before_eval: dict[str, Any] | None,
        after_eval: dict[str, Any] | None,
        history_window: int | None = None,
        min_promotions_for_fixture_guard: int = 2,
    ) -> dict[str, Any]:
        state = self._load_promotion_state()
        promotion = state.get("current") or {}
        promoted_after = ((promotion.get("trial") or {}).get("after_eval") or {})
        promoted_results = {
            item.get("fixture_name"): item
            for item in promoted_after.get("results", [])
            if item.get("fixture_name")
        }
        before_results = {
            item.get("fixture_name"): item
            for item in (before_eval or {}).get("results", [])
            if item.get("fixture_name")
        }
        after_results = {
            item.get("fixture_name"): item
            for item in (after_eval or {}).get("results", [])
            if item.get("fixture_name")
        }

        promoted_passed_fixtures = sorted(name for name, item in promoted_results.items() if item.get("passed"))
        regressed_from_promoted: list[str] = []
        degraded_vs_promoted_baseline: list[str] = []
        for fixture_name in promoted_passed_fixtures:
            after_item = after_results.get(fixture_name)
            before_item = before_results.get(fixture_name)
            if not after_item or not after_item.get("passed"):
                regressed_from_promoted.append(fixture_name)
            if (before_item and before_item.get("passed")) and (not after_item or not after_item.get("passed")):
                degraded_vs_promoted_baseline.append(fixture_name)

        history = list(state.get("history", []))
        if history_window and history_window > 0:
            history = history[-history_window:]
        fixture_pass_counts: dict[str, int] = {}
        fixture_last_promoted_at: dict[str, str] = {}
        for snapshot in history:
            snapshot_timestamp = str(snapshot.get("timestamp") or "")
            snapshot_after = ((snapshot.get("trial") or {}).get("after_eval") or {})
            for item in snapshot_after.get("results", []):
                fixture_name = item.get("fixture_name")
                if not fixture_name or not item.get("passed"):
                    continue
                fixture_pass_counts[fixture_name] = fixture_pass_counts.get(fixture_name, 0) + 1
                fixture_last_promoted_at[fixture_name] = snapshot_timestamp

        historically_protected_fixtures = sorted(
            fixture_name
            for fixture_name, count in fixture_pass_counts.items()
            if count >= max(1, min_promotions_for_fixture_guard)
        )
        regressed_from_promotion_history: list[str] = []
        degraded_vs_promotion_history: list[str] = []
        for fixture_name in historically_protected_fixtures:
            after_item = after_results.get(fixture_name)
            before_item = before_results.get(fixture_name)
            if not after_item or not after_item.get("passed"):
                regressed_from_promotion_history.append(fixture_name)
            if (before_item and before_item.get("passed")) and (not after_item or not after_item.get("passed")):
                degraded_vs_promotion_history.append(fixture_name)

        return {
            "has_promoted_baseline": bool(promotion),
            "promotion_timestamp": promotion.get("timestamp"),
            "promoted_run_id": promotion.get("run_id"),
            "promoted_passed_fixtures": promoted_passed_fixtures,
            "regressed_from_promoted": regressed_from_promoted,
            "degraded_vs_promoted_baseline": degraded_vs_promoted_baseline,
            "promotion_history_depth": len(history),
            "promotion_history_window": history_window,
            "min_promotions_for_fixture_guard": max(1, min_promotions_for_fixture_guard),
            "promotion_pass_counts": fixture_pass_counts,
            "fixture_last_promoted_at": fixture_last_promoted_at,
            "historically_protected_fixtures": historically_protected_fixtures,
            "regressed_from_promotion_history": regressed_from_promotion_history,
            "degraded_vs_promotion_history": degraded_vs_promotion_history,
            "is_safe": len(regressed_from_promoted) == 0 and len(regressed_from_promotion_history) == 0,
        }

    def update_promotion_state(self, *, result: dict[str, Any]) -> dict[str, Any]:
        state = self._load_promotion_state()
        trial = {
            "accepted": result.get("accepted", False),
            "rolled_back": result.get("rolled_back", False),
            "acceptance_reason": result.get("acceptance_reason", ""),
            "before_eval": result.get("before_eval"),
            "after_eval": result.get("after_eval"),
            "ab": result.get("ab"),
            "apply": result.get("apply"),
            "promotion_guard": result.get("promotion_guard"),
        }
        promoted = False
        if result.get("accepted") and not result.get("rolled_back"):
            snapshot = {
                "timestamp": _utc_now(),
                "run_id": (result.get("trace") or {}).get("run_id"),
                "acceptance_reason": result.get("acceptance_reason", ""),
                "trial": trial,
            }
            state["current"] = snapshot
            history = list(state.get("history", []))
            history.append(snapshot)
            state["history"] = history[-10:]
            promoted = True

        self.promotion_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "promoted": promoted,
            "current": state.get("current"),
            "history_count": len(state.get("history", [])),
            "promotion_path": str(self.promotion_path),
        }

    def _append_section(self, path: Path, anchor: str, block: str) -> None:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        marker = f"## {anchor}"
        addition = "\n" + block.strip() + "\n"
        if marker in text:
            updated = text.rstrip() + addition
        else:
            updated = text.rstrip() + f"\n\n{marker}\n" + block.strip() + "\n"
        path.write_text(updated + ("" if updated.endswith("\n") else "\n"), encoding="utf-8")

    def _build_summary(self, entry: dict[str, Any]) -> dict[str, str]:
        status = "accepted" if entry["accepted"] else "rejected"
        fixtures = ", ".join(entry.get("fixture_names", [])) or "n/a"
        todo = (
            f"- [{entry['timestamp']}] Trial {status}; applied={entry['applied_count']}, "
            f"skipped={entry['skipped_count']}, recovered={entry['recovered_count']}, "
            f"regressed={entry['regressed_count']}, rolled_back={entry['rolled_back']}, fixtures={fixtures}."
        )
        verification = "\n".join(
            [
                f"### Trial {entry['timestamp']}",
                f"- Attempted: safe patch trial with {entry['proposal_count']} proposal(s)",
                f"- Verified by: before/after golden evaluation + A/B comparison",
                f"- Actual live state: accepted={entry['accepted']}, rolled_back={entry['rolled_back']}, pass_rate_delta={entry['pass_rate_delta']}",
                f"- Confidence: medium",
            ]
        )
        lesson = "\n".join(
            [
                f"- Date: {entry['timestamp']}",
                f"- Pattern: accepted patch recovered {entry['recovered_count']} failing fixture(s)",
                f"- Rule: preserve recovered behavior in golden fixtures and prefer similarly scoped amendments",
                f"- Example: safe trial on {self.root.name} improved pass rate by {entry['pass_rate_delta']}",
            ]
        )
        gotcha = "\n".join(
            [
                f"- Failure: proposed patch regressed an already-working behavior",
                f"- Trigger: trial {entry['timestamp']} introduced {entry['regressed_count']} regression(s)",
                f"- Prevention: inspect backups/diff summaries first and keep rollback enabled for auto-apply flows",
            ]
        )
        return {
            "todo": todo,
            "verification": verification,
            "lesson": lesson,
            "gotcha": gotcha,
        }

    def _load_preferences(self) -> dict[str, Any]:
        if not self.preferences_path.exists():
            return json.loads(json.dumps(DEFAULT_PREFERENCES))
        raw = json.loads(self.preferences_path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(DEFAULT_PREFERENCES))
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
        proposal = merged.setdefault("proposal", {})
        proposal.setdefault("fixture_policies", {})
        return merged

    def _load_promotion_state(self) -> dict[str, Any]:
        if not self.promotion_path.exists():
            return {"current": None, "history": []}
        try:
            raw = json.loads(self.promotion_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"current": None, "history": []}
        if not isinstance(raw, dict):
            return {"current": None, "history": []}
        raw.setdefault("current", None)
        raw.setdefault("history", [])
        return raw

    def _read_history_entries(self, *, limit: int) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return entries[-limit:]

    def _extract_bullets(self, path: Path, *, limit: int = 8) -> list[str]:
        bullets: list[str] = []
        for line in _safe_read_text(path).splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                bullets.append(stripped[2:])
        return bullets[-limit:]

    def _parse_structured_entries(self, path: Path, *, first_key: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for raw_line in _safe_read_text(path).splitlines():
            line = raw_line.strip()
            if not line.startswith("- ") or ":" not in line:
                continue
            key, value = line[2:].split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == first_key and current:
                entries.append(current)
                current = {}
            current[key] = value
        if current:
            entries.append(current)
        return entries

    def _extract_fixture_names(self, *values: str) -> list[str]:
        names: list[str] = []
        for value in values:
            for match in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]*(?:_test|test_[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+_regression)\b", value):
                names.append(match)
        return _dedupe(names)

    def _build_promotion_profiles(
        self,
        *,
        promotion_state: dict[str, Any],
        history_entries: list[dict[str, Any]],
        proposal_preferences: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        min_promotions = int(proposal_preferences.get("min_promotions_for_fixture_guard", 2) or 2)
        require_test_case = bool(proposal_preferences.get("require_test_case_for_protected_fixtures", False))

        current = promotion_state.get("current") or {}
        current_after = ((current.get("trial") or {}).get("after_eval") or {})
        for item in current_after.get("results", []):
            fixture_name = item.get("fixture_name")
            if not fixture_name:
                continue
            profile = profiles.setdefault(fixture_name, {
                "promoted_pass_count": 0,
                "historically_protected": False,
                "last_promoted_at": "",
                "currently_promoted": False,
                "required_proposal_types": [],
            })
            if item.get("passed"):
                profile["currently_promoted"] = True
                profile["last_promoted_at"] = str(current.get("timestamp") or "")

        history = list(promotion_state.get("history", []))
        for snapshot in history:
            timestamp = str(snapshot.get("timestamp") or "")
            snapshot_after = ((snapshot.get("trial") or {}).get("after_eval") or {})
            for item in snapshot_after.get("results", []):
                fixture_name = item.get("fixture_name")
                if not fixture_name or not item.get("passed"):
                    continue
                profile = profiles.setdefault(fixture_name, {
                    "promoted_pass_count": 0,
                    "historically_protected": False,
                    "last_promoted_at": "",
                    "currently_promoted": False,
                    "required_proposal_types": [],
                })
                profile["promoted_pass_count"] += 1
                profile["last_promoted_at"] = timestamp

        for entry in history_entries:
            if not entry.get("accepted"):
                continue
            for fixture_name in entry.get("fixture_names") or []:
                profile = profiles.setdefault(fixture_name, {
                    "promoted_pass_count": 0,
                    "historically_protected": False,
                    "last_promoted_at": "",
                    "currently_promoted": False,
                    "required_proposal_types": [],
                })
                if entry.get("recovered_count", 0) > 0:
                    profile["promoted_pass_count"] += 1

        for fixture_name, profile in profiles.items():
            if profile["promoted_pass_count"] >= max(1, min_promotions):
                profile["historically_protected"] = True
                required = ["test_case"] if require_test_case else []
                profile["required_proposal_types"] = required

        return dict(sorted(profiles.items()))

    def _build_fixture_profiles(
        self,
        *,
        lesson_entries: list[dict[str, str]],
        gotcha_entries: list[dict[str, str]],
        history_entries: list[dict[str, Any]],
        proposal_preferences: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        fixture_policies = proposal_preferences.get("fixture_policies", {}) if isinstance(proposal_preferences, dict) else {}
        profiles: dict[str, dict[str, Any]] = {}

        def ensure_profile(fixture_name: str) -> dict[str, Any]:
            return profiles.setdefault(
                fixture_name,
                {
                    "lessons": [],
                    "gotchas": [],
                    "boost_terms": [],
                    "avoid_terms": [],
                    "prefer_types": [],
                    "history": {
                        "accepted_count": 0,
                        "rollback_count": 0,
                        "regression_count": 0,
                        "recovery_count": 0,
                    },
                    "policy": {},
                    "regression_prone": False,
                    "recovered_before": False,
                },
            )

        for entry in lesson_entries:
            summary = " | ".join(value for value in entry.values() if value)
            fixtures = self._extract_fixture_names(entry.get("Pattern", ""), entry.get("Rule", ""), entry.get("Example", ""))
            for fixture_name in fixtures:
                profile = ensure_profile(fixture_name)
                profile["lessons"].append(summary)
                if entry.get("Rule"):
                    profile["boost_terms"].append(entry["Rule"])

        for entry in gotcha_entries:
            summary = " | ".join(value for value in entry.values() if value)
            fixtures = self._extract_fixture_names(entry.get("Failure", ""), entry.get("Trigger", ""), entry.get("Prevention", ""))
            for fixture_name in fixtures:
                profile = ensure_profile(fixture_name)
                profile["gotchas"].append(summary)
                if entry.get("Prevention"):
                    profile["avoid_terms"].append(entry["Prevention"])
                profile["regression_prone"] = True

        for entry in history_entries:
            fixture_names = entry.get("fixture_names") or ([] if not entry.get("fixture_name") else [entry.get("fixture_name")])
            for fixture_name in fixture_names:
                if not fixture_name:
                    continue
                profile = ensure_profile(fixture_name)
                history = profile["history"]
                history["accepted_count"] += 1 if entry.get("accepted") else 0
                history["rollback_count"] += 1 if entry.get("rolled_back") else 0
                history["regression_count"] += int(entry.get("regressed_count", 0) or 0)
                history["recovery_count"] += int(entry.get("recovered_count", 0) or 0)
                if history["rollback_count"] > 0 or history["regression_count"] > 0:
                    profile["regression_prone"] = True
                if history["recovery_count"] > 0:
                    profile["recovered_before"] = True

        for fixture_name, policy in fixture_policies.items():
            profile = ensure_profile(fixture_name)
            if isinstance(policy, dict):
                profile["policy"] = dict(policy)
                profile["boost_terms"].extend(policy.get("boost_terms", []))
                profile["avoid_terms"].extend(policy.get("avoid_terms", []))
                profile["prefer_types"].extend(policy.get("prefer_types", []))

        for profile in profiles.values():
            profile["boost_terms"] = _dedupe(profile["boost_terms"])
            profile["avoid_terms"] = _dedupe(profile["avoid_terms"])
            profile["prefer_types"] = _dedupe(profile["prefer_types"])

        return dict(sorted(profiles.items()))
