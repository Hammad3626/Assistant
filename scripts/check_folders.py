"""Validate and display the local folder allowlist."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.actions import DEFAULT_FOLDERS_PATH, ActionError, load_allowed_folders


def main() -> int:
    parser = argparse.ArgumentParser(description="Check safe folder allowlist.")
    parser.add_argument("--folders-path", default=str(DEFAULT_FOLDERS_PATH))
    args = parser.parse_args()

    try:
        folders = load_allowed_folders(args.folders_path)
    except ActionError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Folder allowlist health check")
    print(f"Path: {args.folders_path}")
    for name, target in sorted(folders.items()):
        print(f"- {name}: {target}")
    print("OK: Folder allowlist loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

