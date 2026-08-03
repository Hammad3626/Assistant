"""Safely add a folder to the local allowlist."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.actions import (
    DEFAULT_FOLDERS_PATH,
    ActionError,
    add_allowed_folder,
    load_allowed_folders,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update safe folder allowlist.")
    parser.add_argument("--folders-path", default=str(DEFAULT_FOLDERS_PATH))
    parser.add_argument(
        "--add",
        nargs=2,
        metavar=("NAME", "PATH"),
        help="Add a folder name and existing folder path.",
    )
    parser.add_argument("--show", action="store_true", help="Show folder allowlist and exit.")
    args = parser.parse_args()

    try:
        if args.add:
            name, target = args.add
            folders = add_allowed_folder(name, target, args.folders_path)
            print(f"Added folder: {name} -> {target}")
        else:
            folders = load_allowed_folders(args.folders_path)
    except ActionError as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.show or not args.add:
        print("Allowed folders:")
        for name, target in sorted(folders.items()):
            print(f"- {name}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

