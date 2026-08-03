"""Check the assistant's read-only voice status command."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant voice status command check")
    response = LocalAssistant(use_llm=False).respond("voice status")

    required = (
        "Voice status",
        "Input model path:",
        "Input model found:",
        "Voice output supported:",
        "does not listen or speak",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Voice status is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print("OK: Voice status command is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
