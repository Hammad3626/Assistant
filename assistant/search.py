"""Read-only search across local assistant data."""

from __future__ import annotations

from dataclasses import dataclass

from assistant.history import HistoryError, HistoryStore
from assistant.memory import MemoryError, MemoryStore
from assistant.notes import NotesError, NotesStore
from assistant.tasks import TasksError, TasksStore


class LocalSearchError(RuntimeError):
    """Raised when local data search cannot read one of its stores."""


@dataclass(frozen=True)
class SearchResult:
    source: str
    text: str


class LocalSearch:
    """Search explicit memories, notes, tasks, and local conversation history."""

    def __init__(
        self,
        memory_store: MemoryStore,
        notes_store: NotesStore,
        tasks_store: TasksStore,
        history_store: HistoryStore,
    ) -> None:
        self.memory_store = memory_store
        self.notes_store = notes_store
        self.tasks_store = tasks_store
        self.history_store = history_store

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        clean_query = " ".join(query.strip().lower().split())
        if not clean_query:
            raise LocalSearchError("Search query cannot be empty.")

        results: list[SearchResult] = []
        try:
            for item in self.memory_store.list_memories():
                if clean_query in item.text.lower():
                    results.append(SearchResult("memory", item.text))

            for item in self.notes_store.list_notes():
                if clean_query in item.text.lower():
                    results.append(SearchResult("note", item.text))

            for task in self.tasks_store.list_tasks():
                task_text = task.display_text()
                if clean_query in task_text.lower():
                    status = "done" if task.completed else "open"
                    results.append(SearchResult("task", f"[{status}] {task_text}"))

            for entry in self.history_store.recent(limit=1_000_000):
                if clean_query in entry.text.lower():
                    results.append(SearchResult("history", f"{entry.role}: {entry.text}"))
        except (MemoryError, NotesError, TasksError, HistoryError) as exc:
            raise LocalSearchError(str(exc)) from exc

        return results[:limit]

    def summary(self, query: str, limit: int = 10) -> str:
        results = self.search(query, limit=limit)
        if not results:
            return f"No local results for: {query.strip()}"

        lines = [f"Local search results for: {query.strip()}"]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. [{result.source}] {result.text}")
        return "\n".join(lines)
