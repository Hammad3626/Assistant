"""Check local assistant conversation history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.history import DEFAULT_HISTORY_PATH, HistoryError, HistoryStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant history.")
    parser.add_argument("--history-path", default=str(DEFAULT_HISTORY_PATH))
    args = parser.parse_args()

    store = HistoryStore(args.history_path)
    try:
        entries = store.recent(limit=10)
    except HistoryError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("History health check")
    print(f"Path: {args.history_path}")
    print(f"Recent entries: {len(entries)}")
    print("OK: History loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
