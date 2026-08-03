"""Local JSONL audit log for confirmed or cancelled actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from assistant.actions import PendingAction


DEFAULT_AUDIT_PATH = Path("data/action_audit.jsonl")


class AuditError(RuntimeError):
    """Raised when the local action audit log cannot be read or written."""


@dataclass(frozen=True)
class AuditEntry:
    status: str
    action_kind: str
    description: str
    target: str
    requested_by: str
    result: str
    created_at: str


class ActionAuditStore:
    """Append-only local audit log for action confirmation decisions."""

    def __init__(self, path: str | Path = DEFAULT_AUDIT_PATH, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled

    def record(
        self,
        action: PendingAction,
        status: str,
        requested_by: str,
        result: str,
    ) -> None:
        if not self.enabled:
            return

        entry = {
            "status": status,
            "action_kind": action.kind,
            "description": action.description,
            "target": action.target,
            "requested_by": requested_by,
            "result": result,
            "created_at": _utc_now_iso(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 10) -> list[AuditEntry]:
        if not self.path.exists() or limit <= 0:
            return []

        try:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise AuditError(f"Could not read action audit log: {self.path}") from exc

        entries: list[AuditEntry] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                raw: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            entry = _entry_from_raw(raw)
            if entry:
                entries.append(entry)
        return entries

    def summary(self, limit: int = 10) -> str:
        entries = self.recent(limit=limit)
        if not entries:
            return "No saved action audit entries."

        lines = ["Recent action audit entries:"]
        for entry in entries:
            lines.append(
                f"{entry.status}: {entry.description} -> {entry.result}"
            )
        return "\n".join(lines)

    def clear(self) -> int:
        count = len(self.recent(limit=1_000_000))
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")
        return count


def _entry_from_raw(raw: dict[str, Any]) -> AuditEntry | None:
    fields = {
        "status",
        "action_kind",
        "description",
        "target",
        "requested_by",
        "result",
        "created_at",
    }
    if not all(isinstance(raw.get(field), str) for field in fields):
        return None
    return AuditEntry(
        status=raw["status"],
        action_kind=raw["action_kind"],
        description=raw["description"],
        target=raw["target"],
        requested_by=raw["requested_by"],
        result=raw["result"],
        created_at=raw["created_at"],
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

