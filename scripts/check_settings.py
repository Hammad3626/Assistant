"""Validate local assistant settings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.settings import DEFAULT_SETTINGS_PATH, SettingsError, load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check assistant settings.")
    parser.add_argument("--settings-path", default=str(DEFAULT_SETTINGS_PATH))
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings_path)
    except SettingsError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Settings health check")
    print(f"Path: {args.settings_path}")
    print(settings.summary())
    print("OK: Settings loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

