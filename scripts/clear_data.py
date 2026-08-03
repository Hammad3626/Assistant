"""Clear local assistant memory and/or history with explicit confirmation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.data_tools import clear_data
from assistant.settings import DEFAULT_SETTINGS_PATH, SettingsError, load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear local assistant data.")
    parser.add_argument("--settings-path", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--memory", action="store_true", help="Clear explicit memories.")
    parser.add_argument("--history", action="store_true", help="Clear conversation history.")
    parser.add_argument("--action-audit", action="store_true", help="Clear action audit log.")
    parser.add_argument("--all", action="store_true", help="Clear memory, history, and action audit.")
    parser.add_argument("--yes", action="store_true", help="Required confirmation flag.")
    args = parser.parse_args()

    clear_memory = args.all or args.memory
    clear_history = args.all or args.history
    clear_action_audit = args.all or args.action_audit
    if not clear_memory and not clear_history and not clear_action_audit:
        print("ERROR: Choose --memory, --history, --action-audit, or --all.")
        return 1
    if not args.yes:
        print("ERROR: Refusing to clear data without --yes.")
        return 1

    try:
        settings = load_settings(args.settings_path)
        report = clear_data(
            settings,
            clear_memory=clear_memory,
            clear_history=clear_history,
            clear_action_audit=clear_action_audit,
        )
    except SettingsError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Cleared selected local assistant data.")
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
