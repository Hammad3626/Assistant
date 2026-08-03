"""Check design-only script allowlisting gates without running scripts."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant script allowlist design check")
    assistant = LocalAssistant(use_llm=False)
    response = assistant.respond("script allowlist design")
    print(response.text)

    required = (
        "Explicit script allowlist design",
        "Status: design only",
        "Required static review gates",
        "Required trust gates",
        "SHA-256 hash",
        "confirm script run",
        "No scripts are allowlisted or executed",
    )
    missing = [phrase for phrase in required if phrase not in response.text]
    if missing:
        print("ERROR: Script allowlist design is missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1
    if response.pending_action is not None:
        print("ERROR: Script allowlist design must not create a pending action.")
        return 1

    print("OK: Script allowlist design is read-only and execution remains disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
