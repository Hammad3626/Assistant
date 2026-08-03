"""Append-only local Markdown notes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_NOTES_PATH = Path("data/notes.md")


class NotesError(RuntimeError):
    """Raised when local notes cannot be read or written."""


@dataclass(frozen=True)
class NoteItem:
    text: str
    created_at: str


class NotesStore:
    """Small append-only note store saved as Markdown."""

    def __init__(self, path: str | Path = DEFAULT_NOTES_PATH) -> None:
        self.path = Path(path)

    def add(self, text: str) -> NoteItem:
        clean_text = " ".join(text.strip().split())
        if not clean_text:
            raise NotesError("Cannot save an empty note.")

        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        item = NoteItem(text=clean_text, created_at=created_at)

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.write_text("# Local Assistant Notes\n\n", encoding="utf-8")
            with self.path.open("a", encoding="utf-8") as notes_file:
                notes_file.write(f"- {item.created_at} - {item.text}\n")
        except OSError as exc:
            raise NotesError(f"Could not write notes file: {self.path}") from exc

        return item

    def list_notes(self) -> list[NoteItem]:
        if not self.path.exists():
            return []

        try:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise NotesError(f"Could not read notes file: {self.path}") from exc

        notes: list[NoteItem] = []
        for line in lines:
            if not line.startswith("- "):
                continue
            body = line[2:].strip()
            created_at, separator, text = body.partition(" - ")
            if separator and text:
                notes.append(NoteItem(text=text, created_at=created_at))
        return notes

    def summary(self, limit: int = 10) -> str:
        notes = self.list_notes()
        if not notes:
            return "No saved notes."

        shown = notes[-limit:]
        lines = ["Saved notes:"]
        for index, item in enumerate(shown, start=1):
            lines.append(f"{index}. {item.text}")
        return "\n".join(lines)
