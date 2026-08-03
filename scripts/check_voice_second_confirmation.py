"""Check low-confidence voice confirmation safety without recording audio."""

from __future__ import annotations

from assistant.cli import (
    is_confirmation,
    is_second_voice_confirmation,
    low_confidence_voice_confirmation_text,
    requires_second_voice_confirmation,
)
from assistant.core import LocalAssistant


def main() -> int:
    print("Local PC Assistant low-confidence voice confirmation check")

    if not requires_second_voice_confirmation("low"):
        print("ERROR: Low-confidence voice actions should require a second phrase.")
        return 1
    if not requires_second_voice_confirmation("unavailable"):
        print("ERROR: Unavailable-confidence voice actions should require a second phrase.")
        return 1
    if requires_second_voice_confirmation("high"):
        print("ERROR: High-confidence voice actions should not require the extra phrase.")
        return 1
    if not is_confirmation("yes") or is_second_voice_confirmation("yes"):
        print("ERROR: Plain yes should remain a first confirmation, not the extra phrase.")
        return 1
    if not is_second_voice_confirmation("confirm action"):
        print("ERROR: The second spoken confirmation phrase was not recognized.")
        return 1

    prompt = low_confidence_voice_confirmation_text("low")
    print(prompt)
    if "confirm action" not in prompt or "Voice confidence was low" not in prompt:
        print("ERROR: Low-confidence prompt is missing required safety text.")
        return 1

    response = LocalAssistant(use_llm=False).respond("voice confidence")
    if "confirm action" not in response.text:
        print("ERROR: Voice confidence command does not mention the extra phrase.")
        return 1

    print("OK: Low-confidence spoken actions require a second confirmation phrase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
