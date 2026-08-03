"""Export local assistant memory and history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.data_tools import export_data
from assistant.settings import DEFAULT_SETTINGS_PATH, SettingsError, load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Export local assistant data.")
    parser.add_argument("--settings-path", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--output-dir", default="exports")
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings_path)
        export_dir = export_data(settings, args.output_dir)
    except (SettingsError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Exported local assistant data to: {export_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
