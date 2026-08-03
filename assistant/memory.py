"""Explicit local memory storage for the assistant."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_MEMORY_PATH = Path("data/memory.json")


class MemoryError(RuntimeError):
    """Raised when local memory cannot be loaded or saved."""


@dataclass(frozen=True)
class MemoryItem:
    text: str
    created_at: str


@dataclass(frozen=True)
class DeletedMemoryItem:
    text: str
    created_at: str
    deleted_at: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MemoryStore:
    """Simple explicit memory store backed by one local JSON file."""

    def __init__(self, path: str | Path = DEFAULT_MEMORY_PATH) -> None:
        self.path = Path(path)

    def list_memories(self) -> list[MemoryItem]:
        return self._memories_from_raw(self._read_raw())

    def list_deleted_memories(self) -> list[DeletedMemoryItem]:
        return self._deleted_memories_from_raw(self._read_raw())

    def _memories_from_raw(self, raw: dict[str, Any]) -> list[MemoryItem]:
        items = raw.get("memories", [])
        if not isinstance(items, list):
            raise MemoryError("Memory file has invalid 'memories' value.")

        memories: list[MemoryItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            created_at = item.get("created_at")
            if isinstance(text, str) and isinstance(created_at, str):
                memories.append(MemoryItem(text=text, created_at=created_at))
        return memories

    def _deleted_memories_from_raw(self, raw: dict[str, Any]) -> list[DeletedMemoryItem]:
        items = raw.get("deleted_memories", [])
        if not isinstance(items, list):
            raise MemoryError("Memory file has invalid 'deleted_memories' value.")

        deleted: list[DeletedMemoryItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            created_at = item.get("created_at")
            deleted_at = item.get("deleted_at")
            if isinstance(text, str) and isinstance(created_at, str) and isinstance(deleted_at, str):
                deleted.append(
                    DeletedMemoryItem(
                        text=text,
                        created_at=created_at,
                        deleted_at=deleted_at,
                    )
                )
        return deleted

    def remember(self, text: str) -> MemoryItem:
        clean_text = text.strip()
        if not clean_text:
            raise MemoryError("Cannot remember empty text.")

        item = MemoryItem(text=clean_text, created_at=_utc_now_iso())
        memories = self.list_memories()
        memories.append(item)
        self._write_memories(memories)
        return item

    def clear(self) -> int:
        count = len(self.list_memories())
        self._write_memories([])
        return count

    def rename(self, memory_number: int, new_text: str) -> MemoryItem:
        clean_text = " ".join(new_text.strip().split())
        if not clean_text:
            raise MemoryError("Memory text cannot be empty.")

        raw = self._read_raw()
        memories = self._memories_from_raw(raw)
        target_index = self._memory_index(memories, memory_number)
        original = memories[target_index]
        updated = MemoryItem(text=clean_text, created_at=original.created_at)
        memories[target_index] = updated
        self._write_all(memories, self._deleted_memories_from_raw(raw))
        return updated

    def delete(self, memory_number: int) -> MemoryItem:
        raw = self._read_raw()
        memories = self._memories_from_raw(raw)
        target_index = self._memory_index(memories, memory_number)
        removed = memories.pop(target_index)
        deleted = self._deleted_memories_from_raw(raw)
        deleted.append(
            DeletedMemoryItem(
                text=removed.text,
                created_at=removed.created_at,
                deleted_at=_utc_now_iso(),
            )
        )
        self._write_all(memories, deleted)
        return removed

    def restore_deleted(self, memory_number: int) -> MemoryItem:
        raw = self._read_raw()
        memories = self._memories_from_raw(raw)
        deleted = self._deleted_memories_from_raw(raw)
        if memory_number < 1 or memory_number > len(deleted):
            raise MemoryError(f"Deleted memory number must be between 1 and {len(deleted)}.")

        restored_deleted = deleted.pop(memory_number - 1)
        restored = MemoryItem(text=restored_deleted.text, created_at=restored_deleted.created_at)
        memories.append(restored)
        self._write_all(memories, deleted)
        return restored

    def summary(self) -> str:
        memories = self.list_memories()
        if not memories:
            return "No saved memories."

        lines = ["Saved memories:"]
        for index, item in enumerate(memories, start=1):
            lines.append(f"{index}. {item.text}")
        return "\n".join(lines)

    def deleted_summary(self) -> str:
        deleted = self.list_deleted_memories()
        if not deleted:
            return "Memory trash is empty."

        lines = ["Memory trash:"]
        for index, item in enumerate(deleted, start=1):
            lines.append(f"{index}. {item.text} (deleted {item.deleted_at})")
        return "\n".join(lines)

    @staticmethod
    def _memory_index(memories: list[MemoryItem], memory_number: int) -> int:
        if memory_number < 1 or memory_number > len(memories):
            raise MemoryError(f"Memory number must be between 1 and {len(memories)}.")
        return memory_number - 1

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"memories": []}

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MemoryError(f"Invalid memory JSON: {self.path}") from exc
        except OSError as exc:
            raise MemoryError(f"Could not read memory file: {self.path}") from exc

        if not isinstance(raw, dict):
            raise MemoryError("Memory file must contain a JSON object.")
        return raw

    def _write_memories(self, memories: list[MemoryItem]) -> None:
        deleted = self.list_deleted_memories()
        self._write_all(memories, deleted)

    def _write_all(
        self,
        memories: list[MemoryItem],
        deleted_memories: list[DeletedMemoryItem],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "memories": [
                {"text": item.text, "created_at": item.created_at}
                for item in memories
            ],
            "deleted_memories": [
                {
                    "text": item.text,
                    "created_at": item.created_at,
                    "deleted_at": item.deleted_at,
                }
                for item in deleted_memories
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

