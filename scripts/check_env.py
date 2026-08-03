"""Environment smoke test for the local assistant project.

This script intentionally uses only the Python standard library so Milestone 1
can run before any third-party dependencies are installed.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys


def command_version(command: str) -> str:
    """Return a short version/status string for an optional local command."""
    path = shutil.which(command)
    if path is None:
        return "not found"

    try:
        result = subprocess.run(
            [command, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - diagnostic path
        return f"found at {path}, but version check failed: {exc}"

    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else f"found at {path}"


def main() -> int:
    print("Local PC Assistant environment check")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Executable: {sys.executable}")
    print(f"Platform: {platform.platform()}")
    print(f"Ollama: {command_version('ollama')}")

    if sys.version_info < (3, 11):
        print("ERROR: Python 3.11 or newer is required.")
        return 1

    print("OK: Environment is ready for Milestone 2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

