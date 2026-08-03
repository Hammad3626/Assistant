"""Check the assistant's read-only about command."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant about command check")
    response = LocalAssistant(name="Eva", use_llm=False).respond("about")

    required = (
        "About Eva",
        "Version:",
        "Architecture:",
        "Ollama",
        "Vosk",
        "allowlisted",
        "Useful commands:",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: About command is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print("OK: About command is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
