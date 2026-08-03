"""Check safe suggestions for mistyped assistant commands."""

from __future__ import annotations

from assistant.command_suggestions import suggest_commands, unknown_command_text


def main() -> int:
    print("Local PC Assistant command suggestion check")

    if "memories" not in suggest_commands("memoris"):
        print("ERROR: Expected 'memoris' to suggest 'memories'.")
        return 1

    text = unknown_command_text("opne calculator")
    if "open calculator" not in text or "Did you mean" not in text:
        print("ERROR: Expected typo response to include a safe suggestion.")
        return 1

    if suggest_commands("explain local models"):
        print("ERROR: Normal questions should not produce command suggestions.")
        return 1

    print("OK: Command suggestions are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
