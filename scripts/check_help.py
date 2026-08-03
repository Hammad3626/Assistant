"""Check focused offline help topics."""

from __future__ import annotations

from assistant.command_help import command_help_text, help_topics_text


def main() -> int:
    print("Local PC Assistant focused help check")

    topics = help_topics_text()
    if "tasks" not in topics or "memory" not in topics:
        print("ERROR: Help topic list is missing expected topics.")
        return 1

    tasks = command_help_text("tasks")
    if "todo <task>" not in tasks or "done <task number>" not in tasks:
        print("ERROR: Task help is missing expected commands.")
        return 1

    voice = command_help_text("voice")
    if "--voice" not in voice or "--wake" not in voice or "Vosk" not in voice:
        print("ERROR: Voice help is missing expected local voice details.")
        return 1

    print("OK: Focused help topics are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
