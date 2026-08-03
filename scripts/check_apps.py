"""Validate and display the local app allowlist."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.actions import DEFAULT_APPS_PATH, ActionError, load_allowed_apps


def main() -> int:
    parser = argparse.ArgumentParser(description="Check safe app allowlist.")
    parser.add_argument("--apps-path", default=str(DEFAULT_APPS_PATH))
    args = parser.parse_args()

    try:
        apps = load_allowed_apps(args.apps_path)
    except ActionError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("App allowlist health check")
    print(f"Path: {args.apps_path}")
    for name, target in sorted(apps.items()):
        print(f"- {name}: {target}")
    print("OK: App allowlist loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
