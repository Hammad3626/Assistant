"""Offline launch command reference for the local assistant."""

from __future__ import annotations


def launch_commands_text() -> str:
    """Return exact local startup commands for common assistant modes."""
    return "\n".join(
        [
            "Launch commands",
            "Command-line:",
            "- python -m assistant.cli",
            "- python -m assistant.cli --no-llm",
            "- python -m assistant.cli --model smollm2:135m --num-gpu 0",
            "",
            "Voice:",
            "- python -m assistant.cli --voice --voice-timeout 10",
            "- python -m assistant.cli --speak",
            "- python -m assistant.cli --voice --speak --voice-timeout 10",
            "- python -m assistant.cli --wake --speak",
            "",
            "GUI:",
            "- python -m assistant.gui",
            "- python -m assistant.gui --no-llm",
            "",
            "Checks:",
            "- python -m unittest discover -s tests",
            "- python scripts/check_all.py",
            "- python scripts/check_ollama.py --model smollm2:135m --num-gpu 0",
            "",
            "PowerShell note: if .ps1 scripts are blocked, use these direct python commands.",
        ]
    )
