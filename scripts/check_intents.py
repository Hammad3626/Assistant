"""Check deterministic natural command understanding."""

from __future__ import annotations

from assistant.core import LocalAssistant
from assistant.intent_parser import normalize_intent


def main() -> int:
    print("Local PC Assistant intent check")

    expected = {
        "what can you do for me?": "help",
        "show installed models": "models",
        "open google chrome": "open chrome",
        "open drive c": "open C drive",
        "remind me to call dentist": "todo call dentist",
        "save memory that I prefer short answers": "remember I prefer short answers",
        "show drives": "detected drives",
    }
    for phrase, command in expected.items():
        actual = normalize_intent(phrase)
        if actual != command:
            print(f"ERROR: {phrase!r} normalized to {actual!r}, expected {command!r}")
            return 1

    assistant = LocalAssistant(use_llm=False)
    help_response = assistant.respond("what can you do for me?")
    chrome_response = assistant.respond("open google chrome")
    blocked_response = assistant.respond(r"open C:\Windows\System32\cmd.exe")

    if "Available commands" not in help_response.text:
        print("ERROR: natural help phrase did not reach help command.")
        return 1
    if "Please confirm" not in chrome_response.text or chrome_response.pending_action is None:
        print("ERROR: natural Chrome phrase did not reach confirmation-gated action.")
        return 1
    if "Unlisted apps, scripts, files, and folders cannot open" not in blocked_response.text:
        print("ERROR: arbitrary path open was not blocked.")
        return 1

    print("OK: Natural command understanding maps to existing safe commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
