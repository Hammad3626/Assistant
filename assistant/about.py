"""Offline about and architecture text for the local assistant."""

from __future__ import annotations

from assistant import __version__


def about_text(name: str = "Jarvis") -> str:
    """Return a compact local architecture summary."""
    return "\n".join(
        [
            f"About {name}",
            f"Version: {__version__}",
            "Architecture:",
            "- Python package: assistant",
            "- Interfaces: command line and Tkinter GUI",
            "- Local LLM: Ollama, optional and local-only",
            "- Voice input: Vosk local speech recognition",
            "- Voice output: Windows System.Speech",
            "- Local data: memory, notes, tasks, outbox drafts, history, action audit, settings, aliases",
            "- Safety: apps, folders, and named shell commands are allowlisted and require confirmation",
            "- Boundaries: no raw arbitrary shell commands, permanent file deletion, message/email sending, or network requests",
            "Useful commands: status, models, voice status, paths, outbox, shell commands, command reference.",
        ]
    )
