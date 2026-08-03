"""Safely update local assistant settings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.settings import DEFAULT_SETTINGS_PATH, SETTING_TYPES, SettingsError, load_settings, update_settings_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely update assistant settings.")
    parser.add_argument("--settings-path", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--show", action="store_true", help="Print current settings and exit.")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set a value, for example --set assistant_name=Friday.",
    )
    parser.add_argument("--list-keys", action="store_true", help="List editable setting keys.")
    args = parser.parse_args()

    if args.list_keys:
        print("Editable settings:")
        for key, value_type in SETTING_TYPES.items():
            print(f"- {key} ({value_type.__name__})")
        return 0

    if args.show or not args.set:
        try:
            settings = load_settings(args.settings_path)
        except SettingsError as exc:
            print(f"ERROR: {exc}")
            return 1
        print(settings.summary())
        return 0

    updates: dict[str, str] = {}
    for item in args.set:
        if "=" not in item:
            print(f"ERROR: Expected KEY=VALUE, got: {item}")
            return 1
        key, value = item.split("=", 1)
        updates[key.strip()] = value.strip()

    try:
        settings = update_settings_file(updates, args.settings_path)
    except SettingsError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Updated settings:")
    print(settings.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
