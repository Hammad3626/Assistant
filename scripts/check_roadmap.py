"""Check the assistant's read-only roadmap command."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant roadmap command check")
    response = LocalAssistant(name="Eva", use_llm=False).respond("roadmap")

    required = (
        "Eva roadmap",
        "Working now:",
        "Recommended next upgrades:",
        "Not planned until safety is designed:",
        "GUI settings panel",
        "Confirmation-gated named safe shell command runner",
        "Raw arbitrary shell command execution",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Roadmap command is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print("OK: Roadmap command is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
