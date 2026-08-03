"""Check read-only Windows folder and drive detection."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant Windows detection check")
    assistant = LocalAssistant(use_llm=False)
    for command, expected in (
        ("detected folders", "Detected Windows folders"),
        ("detected drives", "Detected Windows drives"),
        ("detected locations", "Detected Windows folders"),
    ):
        response = assistant.respond(command)
        print(f"> {command}")
        print(response.text)
        if expected not in response.text:
            print(f"ERROR: expected text not found: {expected}")
            return 1
        if "Nothing was added" not in response.text and "none found" not in response.text:
            print("ERROR: detection output must state that it is read-only.")
            return 1

    print("OK: Windows folder and drive detection is read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
