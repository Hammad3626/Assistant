"""Check local assistant notes."""

from __future__ import annotations

import argparse

from assistant.notes import DEFAULT_NOTES_PATH, NotesError, NotesStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant notes.")
    parser.add_argument("--notes-path", default=str(DEFAULT_NOTES_PATH))
    args = parser.parse_args()

    store = NotesStore(args.notes_path)
    print("Local assistant notes check")
    print(f"Path: {args.notes_path}")
    try:
        notes = store.list_notes()
    except NotesError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Saved notes: {len(notes)}")
    print("OK: Notes loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
