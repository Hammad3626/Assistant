"""Safely add an app to the local allowlist."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.actions import DEFAULT_APPS_PATH, ActionError, add_allowed_app, load_allowed_apps


def main() -> int:
    parser = argparse.ArgumentParser(description="Update safe app allowlist.")
    parser.add_argument("--apps-path", default=str(DEFAULT_APPS_PATH))
    parser.add_argument("--add", nargs=2, metavar=("NAME", "EXE"), help="Add an app name and .exe target.")
    parser.add_argument("--show", action="store_true", help="Show app allowlist and exit.")
    args = parser.parse_args()

    try:
        if args.add:
            name, target = args.add
            apps = add_allowed_app(name, target, args.apps_path)
            print(f"Added app: {name} -> {target}")
        else:
            apps = load_allowed_apps(args.apps_path)
    except ActionError as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.show or not args.add:
        print("Allowed apps:")
        for name, target in sorted(apps.items()):
            print(f"- {name}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
