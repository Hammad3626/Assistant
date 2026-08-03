"""Check local assistant search across memory, notes, and history."""

from __future__ import annotations

import argparse

from assistant.history import HistoryStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.search import LocalSearch, LocalSearchError
from assistant.settings import load_settings
from assistant.tasks import TasksStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant search.")
    parser.add_argument("--settings-path", default="config/settings.json")
    parser.add_argument("--query", default="test")
    args = parser.parse_args()

    print("Local assistant search check")
    print(f"Settings: {args.settings_path}")
    print(f"Query: {args.query}")
    settings = load_settings(args.settings_path)
    search = LocalSearch(
        MemoryStore(settings.memory_path),
        NotesStore(settings.notes_path),
        TasksStore(settings.tasks_path),
        HistoryStore(settings.history_path, enabled=settings.history_enabled),
    )

    try:
        results = search.search(args.query)
    except LocalSearchError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Results: {len(results)}")
    print("OK: Search completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
