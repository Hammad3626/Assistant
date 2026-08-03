"""Configurable local persona text for LLM prompting."""

from __future__ import annotations

from pathlib import Path


DEFAULT_PERSONA_PATH = Path("config/persona.txt")

SAFETY_FOOTER = (
    "Non-negotiable safety rules:\n"
    "- Do not claim you opened apps, changed files, sent messages, or ran commands.\n"
    "- If the user asks for computer control, say it must use the assistant's confirmation flow.\n"
    "- Do not provide instructions for deleting or damaging user files."
)


class PersonaError(RuntimeError):
    """Raised when the local persona file cannot be loaded."""


def load_persona(path: str | Path = DEFAULT_PERSONA_PATH) -> str:
    persona_path = Path(path)
    if not persona_path.exists():
        return default_persona()

    try:
        text = persona_path.read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise PersonaError(f"Could not read persona file: {persona_path}") from exc

    if not text:
        raise PersonaError("Persona file cannot be empty.")
    if len(text) > 4000:
        raise PersonaError("Persona file is too long; keep it under 4000 characters.")

    return text


def default_persona() -> str:
    return (
        "You are a local offline PC assistant. Answer briefly and clearly.\n"
        "Be practical, calm, and beginner-friendly.\n"
        "Use saved memories only when they are relevant to the user's request."
    )


def build_system_prompt(persona_text: str) -> str:
    return f"{persona_text.strip()}\n\n{SAFETY_FOOTER}"

