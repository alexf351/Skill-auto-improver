from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class StepResult:
    name: str
    output: dict[str, Any]
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None

    def finish(self) -> None:
        self.finished_at = utc_now_iso()


@dataclass(slots=True)
class RunTrace:
    skill_path: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "running"
    created_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    steps: list[StepResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: StepResult) -> None:
        self.steps.append(step)

    def complete(self, status: str = "ok") -> None:
        self.status = status
        self.finished_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_version": 1,
            "run_id": self.run_id,
            "skill_path": self.skill_path,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "metadata": self.metadata,
            "steps": [
                {
                    "name": s.name,
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                    "output": s.output,
                }
                for s in self.steps
            ],
        }
