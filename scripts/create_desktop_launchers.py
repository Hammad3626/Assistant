"""Create Desktop batch launchers for the local assistant.

This writes small .bat files to the current user's Desktop. The launchers call
back into this project folder and do not bypass the assistant's confirmations.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"

LAUNCHERS = {
    "Local Assistant GUI.bat": "python -m assistant.gui",
    "Local Assistant CLI.bat": "python -m assistant.cli",
    "Local Assistant Voice.bat": "python -m assistant.cli --voice --speak",
}


def launcher_text(command: str, pause: bool) -> str:
    lines = [
        "@echo off",
        f'cd /d "{PROJECT_ROOT}"',
        command,
    ]
    if pause:
        lines.append("pause")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not DESKTOP.exists():
        print(f"ERROR: Desktop folder not found: {DESKTOP}")
        return 1

    print(f"Creating Desktop launchers in: {DESKTOP}")
    for name, command in LAUNCHERS.items():
        path = DESKTOP / name
        pause = "GUI" not in name
        path.write_text(launcher_text(command, pause=pause), encoding="ascii")
        print(f"Created: {path}")

    print("OK: Desktop launchers created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
