"""Check the assistant's read-only path report command."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant path report check")
    response = LocalAssistant(use_llm=False).respond("paths")

    required = (
        "Local assistant paths",
        "Settings:",
        "Memory:",
        "Notes:",
        "Tasks:",
        "Voice model:",
        "read-only",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Path report is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print("OK: Path report command is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
