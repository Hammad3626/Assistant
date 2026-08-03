"""Read-only voice safety drill text."""

from __future__ import annotations

def voice_safety_drill_text() -> str:
    """Return a no-microphone simulation of low-confidence voice confirmation."""
    second_phrase = "confirm action"
    first_prompt = (
        "Voice confidence was low. For safety, say "
        f"'{second_phrase}' to run this action, or say 'no' to cancel."
    )
    return "\n".join(
        [
            "Voice safety drill",
            "Read-only simulation. No microphone is used, no app opens, and no action is queued.",
            "",
            "Scenario:",
            "- Heard command: open calculator",
            "- Confidence: low",
            "- Pending action preview: Open calculator",
            "",
            "Simulated flow:",
            "1. Say 'yes' after reviewing the preview.",
            f"2. Assistant asks: {first_prompt}",
            f"3. Say '{second_phrase}' to complete the simulated approval.",
            "",
            "Safety result:",
            "- In the real voice CLI, low or unavailable confidence needs both phrases.",
            "- Saying the second phrase first does not run the action.",
            "- Saying 'no' or a correction cancels the pending action.",
            "- This drill does not execute, confirm, or save anything.",
        ]
    )
