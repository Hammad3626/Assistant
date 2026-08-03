"""Check read-only voice confidence reporting without recording audio."""

from __future__ import annotations

from assistant.core import LocalAssistant
from assistant.voice_input import analyze_voice_confidence, format_voice_confidence


def main() -> int:
    print("Local PC Assistant voice confidence check")

    report = analyze_voice_confidence(
        {
            "text": "open calculator",
            "result": [
                {"word": "open", "conf": 0.91},
                {"word": "calculator", "conf": 0.84},
            ],
        }
    )
    summary = format_voice_confidence(report)
    print(summary)
    if report.level != "high" or "avg" not in summary:
        print("ERROR: Expected a high-confidence summary from sample Vosk data.")
        return 1

    fallback = analyze_voice_confidence({"text": "hello"})
    print(format_voice_confidence(fallback))
    if fallback.level != "unavailable":
        print("ERROR: Expected unavailable confidence when word scores are missing.")
        return 1

    response = LocalAssistant(use_llm=False).respond("voice confidence")
    required = ("Voice confidence reporting", "read-only", "explicit confirmation")
    missing = [text for text in required if text not in response.text]
    if missing:
        print(f"ERROR: Voice confidence command missing: {', '.join(missing)}")
        return 1

    print("OK: Voice confidence reporting is available and read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
