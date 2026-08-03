"""Check the assistant's local launch command reference."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant launch command check")
    response = LocalAssistant(use_llm=False).respond("launch commands")

    required = (
        "Launch commands",
        "python -m assistant.cli",
        "python -m assistant.gui",
        "python scripts/check_all.py",
        "PowerShell",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Launch command reference is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(response.text)
    print("OK: Launch command reference is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
