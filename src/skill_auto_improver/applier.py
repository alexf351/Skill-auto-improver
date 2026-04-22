from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import difflib
import hashlib
import json
import shutil
from datetime import datetime, timezone

from .proposer import PatchProposal


SUPPORTED_PROPOSAL_TYPES = {"instruction", "artifact", "test_case"}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


@dataclass(slots=True)
class AppliedChange:
    proposal_type: str
    target_path: str
    backup_path: str | None
    status: str
    fixture_name: str | None = None
    detail: str = ""
    backup_id: str | None = None
    diff_summary: dict[str, Any] | None = None


@dataclass(slots=True)
class ApplyReport:
    skill_path: str
    mode: str
    applied: list[AppliedChange] = field(default_factory=list)
    skipped: list[AppliedChange] = field(default_factory=list)

    @property
    def applied_count(self) -> int:
        return len(self.applied)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_path": self.skill_path,
            "mode": self.mode,
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "applied": [asdict(c) for c in self.applied],
            "skipped": [asdict(c) for c in self.skipped],
        }


@dataclass(slots=True)
class BackupEntry:
    target_path: str
    backup_path: str
    created_at: str
    exists: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BackupInspection:
    target_path: str
    backup_path: str
    created_at: str
    exists: bool
    current_exists: bool
    current_diff: dict[str, Any] | None = None
    trial_refs: list[dict[str, Any]] = field(default_factory=list)
    checksum_verified: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RestoreReport:
    skill_path: str
    backup_path: str
    target_path: str
    restored: bool
    detail: str
    checksum_verified: bool = False
    pre_restore_backup_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillPatchApplier:
    """Apply accepted patch proposals to a skill with simple rollback backups."""

    def __init__(self, skill_path: str | Path):
        self.skill_path = Path(skill_path)
        self.skill_md_path = self.skill_path / "SKILL.md"
        self.fixtures_path = self.skill_path / "golden-fixtures.json"
        self.backups_dir = self.skill_path / ".skill-auto-improver" / "backups"

    def apply(
        self,
        proposals: list[PatchProposal],
        *,
        accepted_types: set[str] | None = None,
        mode: str = "apply",
        min_confidence: float = 0.0,
        accepted_severities: set[str] | None = None,
        fixture_policies: dict[str, Any] | None = None,
    ) -> ApplyReport:
        accepted_types = accepted_types or SUPPORTED_PROPOSAL_TYPES
        accepted_severities = accepted_severities or {"info", "warning", "critical"}
        fixture_policies = fixture_policies or {}
        proposal_types_by_fixture = self._proposal_types_by_fixture(proposals)
        report = ApplyReport(skill_path=str(self.skill_path), mode=mode)

        for proposal in proposals:
            policy = fixture_policies.get(proposal.fixture_name, {}) if proposal.fixture_name else {}
            effective_min_confidence = float(policy.get("min_confidence", min_confidence) or 0.0)
            severity_values = policy.get("accepted_severities") or accepted_severities
            effective_accepted_severities = set(severity_values) if severity_values else {"info", "warning", "critical"}
            required_types = set(policy.get("required_proposal_types") or [])
            present_types = proposal_types_by_fixture.get(proposal.fixture_name, set())

            if proposal.type not in accepted_types:
                report.skipped.append(
                    AppliedChange(
                        proposal_type=proposal.type,
                        target_path="",
                        backup_path=None,
                        status="skipped",
                        detail="proposal type not accepted",
                    )
                )
                continue

            if required_types and not required_types.issubset(present_types):
                report.skipped.append(
                    AppliedChange(
                        proposal_type=proposal.type,
                        target_path="",
                        backup_path=None,
                        status="skipped",
                        detail=(
                            f"fixture '{proposal.fixture_name or 'unknown'}' requires proposal types "
                            f"{sorted(required_types)} before auto-apply"
                        ),
                    )
                )
                continue

            if proposal.confidence < effective_min_confidence:
                report.skipped.append(
                    AppliedChange(
                        proposal_type=proposal.type,
                        target_path="",
                        backup_path=None,
                        status="skipped",
                        detail=(
                            f"proposal confidence {proposal.confidence:.2f} below minimum "
                            f"{effective_min_confidence:.2f}"
                        ),
                    )
                )
                continue

            if proposal.severity not in effective_accepted_severities:
                report.skipped.append(
                    AppliedChange(
                        proposal_type=proposal.type,
                        target_path="",
                        backup_path=None,
                        status="skipped",
                        detail=(
                            f"proposal severity '{proposal.severity}' not accepted"
                            f" for fixture '{proposal.fixture_name or 'unknown'}'"
                        ),
                    )
                )
                continue

            if proposal.type == "instruction":
                change = self._apply_instruction(proposal, mode=mode)
            elif proposal.type == "artifact":
                change = self._apply_artifact(proposal, mode=mode)
            elif proposal.type == "test_case":
                change = self._apply_test_case(proposal, mode=mode)
            else:
                change = AppliedChange(
                    proposal_type=proposal.type,
                    target_path="",
                    backup_path=None,
                    status="skipped",
                    detail="unsupported proposal type",
                )

            if change.status == "applied":
                report.applied.append(change)
            else:
                report.skipped.append(change)

        return report

    def list_backups(self) -> list[BackupEntry]:
        if not self.backups_dir.exists():
            return []

        entries: list[BackupEntry] = []
        for backup_path in sorted(self.backups_dir.glob("*.bak"), reverse=True):
            target_name, created_at = self._parse_backup_name(backup_path.name)
            entries.append(
                BackupEntry(
                    target_path=str(self.skill_path / target_name),
                    backup_path=str(backup_path),
                    created_at=created_at,
                    exists=backup_path.exists(),
                )
            )
        return entries

    def inspect_backups(
        self,
        *,
        limit: int | None = None,
        target_name: str | None = None,
        history_entries: list[dict[str, Any]] | None = None,
    ) -> list[BackupInspection]:
        inspections: list[BackupInspection] = []
        entries = self.list_backups()
        history_by_backup_id = self._history_by_backup_id(history_entries or [])
        if target_name:
            entries = [entry for entry in entries if Path(entry.target_path).name == target_name]
        for entry in entries[:limit]:
            backup_path = Path(entry.backup_path)
            target_path = Path(entry.target_path)
            current_exists = target_path.exists()
            current_diff = None
            backup_id = self._backup_id(backup_path)
            if entry.exists and current_exists:
                current_diff = self._build_diff_summary(
                    backup_path.read_text(encoding="utf-8"),
                    target_path.read_text(encoding="utf-8"),
                    target_path=target_path,
                )
            checksum_verified = self._verify_backup_checksum(backup_path) if entry.exists else None
            inspections.append(
                BackupInspection(
                    target_path=entry.target_path,
                    backup_path=entry.backup_path,
                    created_at=entry.created_at,
                    exists=entry.exists,
                    current_exists=current_exists,
                    current_diff=current_diff,
                    trial_refs=history_by_backup_id.get(backup_id or "", []),
                    checksum_verified=checksum_verified,
                )
            )
        return inspections

    def resolve_backup(self, backup_ref: str, *, target_name: str | None = None) -> Path | None:
        candidate = Path(backup_ref)
        if candidate.exists():
            return candidate
        entries = self.list_backups()
        if target_name:
            entries = [entry for entry in entries if Path(entry.target_path).name == target_name]
        for entry in entries:
            if entry.created_at == backup_ref or Path(entry.backup_path).name == backup_ref:
                return Path(entry.backup_path)
        return None

    def restore_backup(self, backup_path: str | Path) -> RestoreReport:
        backup_path = Path(backup_path)
        if not backup_path.exists():
            return RestoreReport(
                skill_path=str(self.skill_path),
                backup_path=str(backup_path),
                target_path="",
                restored=False,
                detail="backup not found",
            )

        checksum_verified = self._verify_backup_checksum(backup_path)
        target_name, _ = self._parse_backup_name(backup_path.name)
        target_path = self.skill_path / target_name
        if not checksum_verified:
            return RestoreReport(
                skill_path=str(self.skill_path),
                backup_path=str(backup_path),
                target_path=str(target_path),
                restored=False,
                detail="backup checksum verification failed",
                checksum_verified=False,
            )

        pre_restore_backup_path = None
        if target_path.exists():
            pre_restore_backup_path = str(self._backup_file(target_path))

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target_path)

        return RestoreReport(
            skill_path=str(self.skill_path),
            backup_path=str(backup_path),
            target_path=str(target_path),
            restored=True,
            detail="backup restored",
            checksum_verified=True,
            pre_restore_backup_path=pre_restore_backup_path,
        )

    def restore_latest_backup(self, *, target_name: str) -> RestoreReport:
        entries = self.list_backups()
        for entry in entries:
            if Path(entry.target_path).name != target_name:
                continue
            return self.restore_backup(entry.backup_path)

        return RestoreReport(
            skill_path=str(self.skill_path),
            backup_path="",
            target_path=str(self.skill_path / target_name),
            restored=False,
            detail=f"no backups found for target '{target_name}'",
        )

    def _apply_instruction(self, proposal: PatchProposal, *, mode: str) -> AppliedChange:
        if not self.skill_md_path.exists():
            return AppliedChange(
                proposal_type=proposal.type,
                target_path=str(self.skill_md_path),
                backup_path=None,
                status="skipped",
                detail="SKILL.md not found",
            )

        suggestion = proposal.content.get("suggestion") or proposal.description
        mismatched_fields = proposal.content.get("mismatched_fields", [])
        heading = "## Auto-Improver Proposed Instruction Update"
        note = (
            f"{heading}\n"
            f"- Fixture: {proposal.fixture_name}\n"
            f"- Severity: {proposal.severity}\n"
            f"- Mismatched fields: {', '.join(mismatched_fields) if mismatched_fields else 'n/a'}\n"
            f"- Suggestion: {suggestion}\n"
        )

        current = self.skill_md_path.read_text(encoding="utf-8")
        updated, action = self._merge_markdown_section(
            current,
            heading=heading,
            block=note,
            fixture_name=proposal.fixture_name,
            allow_heading_fallback=False,
        )
        if updated == current:
            return AppliedChange(
                proposal_type=proposal.type,
                target_path=str(self.skill_md_path),
                backup_path=None,
                status="skipped",
                detail="instruction note already up to date",
                diff_summary=self._build_diff_summary(current, updated, target_path=self.skill_md_path),
            )

        diff_summary = self._build_diff_summary(current, updated, target_path=self.skill_md_path)
        backup_path = self._backup_file(self.skill_md_path) if mode == "apply" else None
        if mode == "apply":
            self.skill_md_path.write_text(updated, encoding="utf-8")

        return AppliedChange(
            proposal_type=proposal.type,
            target_path=str(self.skill_md_path),
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            fixture_name=proposal.fixture_name,
            detail=f"instruction note {action}",
            backup_id=self._backup_id(backup_path),
            diff_summary=diff_summary,
        )

    def _apply_artifact(self, proposal: PatchProposal, *, mode: str) -> AppliedChange:
        target_path = proposal.content.get("target_path")
        body = proposal.content.get("body")
        section_title = proposal.content.get("section_title") or f"Auto-Improver update for {proposal.fixture_name}"
        if not target_path or not body:
            return AppliedChange(
                proposal_type=proposal.type,
                target_path=str(self.skill_path),
                backup_path=None,
                status="skipped",
                detail="missing artifact target or body",
            )

        resolved = (self.skill_path / target_path).resolve()
        skill_root = self.skill_path.resolve()
        if not str(resolved).startswith(str(skill_root)):
            return AppliedChange(
                proposal_type=proposal.type,
                target_path=str(resolved),
                backup_path=None,
                status="skipped",
                detail="artifact target escapes skill root",
            )

        heading = f"# {section_title}"
        note = f"{heading}\n\n{body.rstrip()}\n"
        current = resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        updated, action = self._merge_markdown_section(
            current,
            heading=heading,
            block=note,
            fixture_name=proposal.fixture_name,
            allow_heading_fallback=True,
        )
        if updated == current:
            return AppliedChange(
                proposal_type=proposal.type,
                target_path=str(resolved),
                backup_path=None,
                status="skipped",
                detail="artifact note already up to date",
                diff_summary=self._build_diff_summary(current, updated, target_path=resolved),
            )

        diff_summary = self._build_diff_summary(current, updated, target_path=resolved)
        backup_path = self._backup_file(resolved) if (mode == "apply" and resolved.exists()) else None
        if mode == "apply":
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(updated, encoding="utf-8")

        return AppliedChange(
            proposal_type=proposal.type,
            target_path=str(resolved),
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            fixture_name=proposal.fixture_name,
            detail=f"artifact note {action}",
            backup_id=self._backup_id(backup_path),
            diff_summary=diff_summary,
        )

    def _apply_test_case(self, proposal: PatchProposal, *, mode: str) -> AppliedChange:
        fixture = proposal.content.get("fixture")
        if not fixture or "name" not in fixture:
            return AppliedChange(
                proposal_type=proposal.type,
                target_path=str(self.fixtures_path),
                backup_path=None,
                status="skipped",
                detail="missing fixture payload",
            )

        existing = []
        if self.fixtures_path.exists():
            existing = json.loads(self.fixtures_path.read_text(encoding="utf-8"))
            for item in existing:
                if item.get("name") == fixture["name"]:
                    return AppliedChange(
                        proposal_type=proposal.type,
                        target_path=str(self.fixtures_path),
                        backup_path=None,
                        status="skipped",
                        detail="fixture already exists",
                    )

        current_text = self.fixtures_path.read_text(encoding="utf-8") if self.fixtures_path.exists() else ""
        next_existing = [*existing, fixture]
        updated_text = json.dumps(next_existing, indent=2, sort_keys=True) + "\n"
        diff_summary = self._build_diff_summary(current_text, updated_text, target_path=self.fixtures_path)

        backup_path = self._backup_file(self.fixtures_path) if (mode == "apply" and self.fixtures_path.exists()) else None
        if mode == "apply":
            self.fixtures_path.write_text(updated_text, encoding="utf-8")

        return AppliedChange(
            proposal_type=proposal.type,
            target_path=str(self.fixtures_path),
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            fixture_name=proposal.fixture_name,
            detail="regression fixture appended",
            backup_id=self._backup_id(backup_path),
            diff_summary=diff_summary,
        )

    def _backup_file(self, path: Path) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        relative_name = path.resolve().relative_to(self.skill_path.resolve()).as_posix().replace("/", "__")
        backup_path = self.backups_dir / f"{relative_name}.{utc_timestamp()}.bak"
        shutil.copy2(path, backup_path)
        self._write_backup_checksum(backup_path)
        return backup_path

    def _backup_id(self, backup_path: Path | None) -> str | None:
        if not backup_path:
            return None
        _, created_at = self._parse_backup_name(backup_path.name)
        return created_at

    def _backup_checksum_path(self, backup_path: Path) -> Path:
        return backup_path.with_suffix(backup_path.suffix + ".sha256")

    def _compute_file_checksum(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _write_backup_checksum(self, backup_path: Path) -> None:
        checksum_path = self._backup_checksum_path(backup_path)
        checksum_path.write_text(self._compute_file_checksum(backup_path) + "\n", encoding="utf-8")

    def _verify_backup_checksum(self, backup_path: Path) -> bool:
        checksum_path = self._backup_checksum_path(backup_path)
        if not checksum_path.exists():
            return False
        expected = checksum_path.read_text(encoding="utf-8").strip()
        if not expected:
            return False
        return self._compute_file_checksum(backup_path) == expected

    def _build_diff_summary(self, before: str, after: str, *, target_path: Path) -> dict[str, Any]:
        diff_lines = list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"before:{target_path.name}",
                tofile=f"after:{target_path.name}",
                lineterm="",
            )
        )
        added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        preview = diff_lines[:12]
        return {
            "target_path": str(target_path),
            "added_lines": added,
            "removed_lines": removed,
            "preview": preview,
        }

    def _merge_markdown_section(
        self,
        current: str,
        *,
        heading: str,
        block: str,
        fixture_name: str,
        allow_heading_fallback: bool,
    ) -> tuple[str, str]:
        normalized_block = block.strip()
        if not current.strip():
            return normalized_block + "\n", "created"
        if normalized_block in current:
            return current, "unchanged"

        lines = current.splitlines()
        fixture_marker = f"- Fixture: {fixture_name}" if fixture_name else ""
        start_index = None
        end_index = None
        for index, line in enumerate(lines):
            if line.strip() != heading:
                continue
            block_end = len(lines)
            for candidate in range(index + 1, len(lines)):
                if lines[candidate].startswith("#"):
                    block_end = candidate
                    break
            block_lines = lines[index:block_end]
            if fixture_marker and any(item.strip() == fixture_marker for item in block_lines):
                start_index = index
                end_index = block_end
                break
            if not fixture_marker and start_index is None:
                start_index = index
                end_index = block_end
                break

        if allow_heading_fallback and start_index is None:
            heading_indexes = [index for index, line in enumerate(lines) if line.strip() == heading]
            if len(heading_indexes) == 1:
                start_index = heading_indexes[0]
                end_index = len(lines)
                for candidate in range(start_index + 1, len(lines)):
                    if lines[candidate].startswith("#"):
                        end_index = candidate
                        break

        if start_index is not None and end_index is not None:
            replacement = normalized_block.splitlines()
            new_lines = lines[:start_index] + replacement + lines[end_index:]
            updated = "\n".join(new_lines).rstrip() + "\n"
            return updated, "updated"

        updated = current.rstrip() + "\n\n" + normalized_block + "\n"
        return updated, "appended"

    def _parse_backup_name(self, backup_name: str) -> tuple[str, str]:
        parts = backup_name.split(".")
        if len(parts) < 4 or parts[-1] != "bak":
            raise ValueError(f"invalid backup name: {backup_name}")
        created_at = parts[-2]
        target_name = ".".join(parts[:-2]).replace("__", "/")
        return target_name, created_at

    def _proposal_types_by_fixture(self, proposals: list[PatchProposal]) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = {}
        for proposal in proposals:
            if not proposal.fixture_name:
                continue
            grouped.setdefault(proposal.fixture_name, set()).add(proposal.type)
        return grouped

    def _history_by_backup_id(self, history_entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in history_entries:
            if not isinstance(entry, dict):
                continue
            for backup_ref in entry.get("backup_refs", []):
                if not isinstance(backup_ref, dict):
                    continue
                backup_id = str(backup_ref.get("backup_id") or "").strip()
                if not backup_id:
                    continue
                grouped.setdefault(backup_id, []).append(
                    {
                        "timestamp": entry.get("timestamp"),
                        "accepted": entry.get("accepted", False),
                        "rolled_back": entry.get("rolled_back", False),
                        "acceptance_reason": entry.get("acceptance_reason", ""),
                        "fixture_names": entry.get("fixture_names", []),
                        "backup_ref": backup_ref,
                    }
                )
        return grouped
