"""Check the assistant's built-in command reference."""

from __future__ import annotations

from assistant.command_reference import command_reference_text


REQUIRED_PHRASES = (
    "Command reference",
    "Basics:",
    "Memory:",
    "Notes:",
    "Tasks:",
    "Safe local actions:",
    "shell commands",
    "run shell",
    "script allowlist design",
    "script review checklist",
    "verify script review checklist",
    "script allowlist preflight",
    "open calculator",
    "App and folder actions require confirmation.",
)


def main() -> int:
    print("Local PC Assistant command reference check")
    reference = command_reference_text()
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in reference]
    if missing:
        print("ERROR: Command reference is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print("OK: Command reference is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
