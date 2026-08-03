"""Check the read-only voice safety drill."""

from __future__ import annotations

from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant voice safety drill check")

    response = LocalAssistant(use_llm=False).respond("voice safety drill")
    print(response.text)

    required = (
        "Voice safety drill",
        "Read-only simulation",
        "No microphone is used",
        "confirm action",
        "does not execute",
    )
    missing = [text for text in required if text not in response.text]
    if missing:
        print(f"ERROR: Voice safety drill missing: {', '.join(missing)}")
        return 1
    if response.pending_action is not None:
        print("ERROR: Voice safety drill queued a real pending action.")
        return 1

    print("OK: Voice safety drill is read-only and uses no microphone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
