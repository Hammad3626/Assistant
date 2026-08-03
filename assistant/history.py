"""Local JSONL conversation history."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_HISTORY_PATH = Path("data/history.jsonl")


class HistoryError(RuntimeError):
    """Raised when local history cannot be loaded or saved."""


@dataclass(frozen=True)
class HistoryEntry:
    role: str
    text: str
    created_at: str


class HistoryStore:
    """Append-only local conversation history store."""

    def __init__(self, path: str | Path = DEFAULT_HISTORY_PATH, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled

    def append(self, role: str, text: str) -> None:
        if not self.enabled or not text.strip():
            return
        entry = {
            "role": role,
            "text": text.strip(),
            "created_at": _utc_now_iso(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 10) -> list[HistoryEntry]:
        if not self.path.exists():
            return []
        if limit <= 0:
            return []

        try:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise HistoryError(f"Could not read history file: {self.path}") from exc

        entries: list[HistoryEntry] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                raw: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            role = raw.get("role")
            text = raw.get("text")
            created_at = raw.get("created_at")
            if isinstance(role, str) and isinstance(text, str) and isinstance(created_at, str):
                entries.append(HistoryEntry(role=role, text=text, created_at=created_at))
        return entries

    def summary(self, limit: int = 10) -> str:
        entries = self.recent(limit=limit)
        if not entries:
            return "No saved conversation history."

        lines = ["Recent conversation history:"]
        for entry in entries:
            lines.append(f"{entry.role}: {entry.text}")
        return "\n".join(lines)

    def clear(self) -> int:
        count = len(self.recent(limit=1_000_000))
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")
        return count


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
