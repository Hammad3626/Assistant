"""Print a local assistant data report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.data_tools import build_report
from assistant.settings import DEFAULT_SETTINGS_PATH, SettingsError, load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Report local assistant data counts.")
    parser.add_argument("--settings-path", default=str(DEFAULT_SETTINGS_PATH))
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings_path)
        report = build_report(settings)
    except SettingsError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
