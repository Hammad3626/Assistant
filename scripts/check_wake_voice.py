"""Check optional wake-loop command parsing without recording audio."""

from __future__ import annotations

from assistant.core import LocalAssistant
from assistant.voice_input import extract_wake_command


def main() -> int:
    print("Local assistant wake voice loop check")

    woke, command = extract_wake_command("hey eva hello")
    if not woke or command != "hello":
        print("ERROR: Wake phrase parser did not extract an inline command.")
        return 1

    ignored, ignored_command = extract_wake_command("hello")
    if ignored or ignored_command:
        print("ERROR: Wake phrase parser accepted speech without the wake phrase.")
        return 1

    response = LocalAssistant(use_llm=False).respond("wake status")
    required = ("Wake voice loop", "--wake --speak", "Safety")
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Wake status is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print("OK: Wake voice loop command parsing is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
