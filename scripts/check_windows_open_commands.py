"""Check safe Windows open commands without executing them."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.core import LocalAssistant
from assistant.windows_detection import detect_drives


def main() -> int:
    print("Local PC Assistant Windows open command check")
    assistant = LocalAssistant(use_llm=False)
    commands = ["open this pc", "open settings", "open chrome"]
    drives = detect_drives()
    if drives:
        commands.insert(0, f"open {drives[0].name}")

    for command in commands:
        response = assistant.respond(command)
        print(f"> {command}")
        print(response.text)
        if "Please confirm" not in response.text or response.pending_action is None:
            print("ERROR: command did not produce a confirmation-gated action.")
            return 1

    print("OK: Windows open commands are confirmation-gated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
