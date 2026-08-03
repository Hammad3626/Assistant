"""Check the local assistant briefing."""

from __future__ import annotations

import argparse

from assistant.briefing import BriefingError, build_briefing
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.settings import load_settings
from assistant.tasks import TasksStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant briefing.")
    parser.add_argument("--settings-path", default="config/settings.json")
    args = parser.parse_args()

    print("Local assistant briefing check")
    print(f"Settings: {args.settings_path}")
    settings = load_settings(args.settings_path)
    try:
        briefing = build_briefing(
            MemoryStore(settings.memory_path),
            NotesStore(settings.notes_path),
            TasksStore(settings.tasks_path),
        )
    except BriefingError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(briefing.summary())
    print("OK: Briefing generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
