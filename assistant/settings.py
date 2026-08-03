"""Local JSON settings for the assistant."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_PATH = Path("config/settings.json")


class SettingsError(RuntimeError):
    """Raised when local settings cannot be loaded or saved."""


@dataclass(frozen=True)
class AssistantSettings:
    assistant_name: str = "Jarvis"
    model: str = "smollm2:135m"
    use_llm: bool = True
    num_gpu: int = 0
    voice_enabled: bool = False
    voice_model_path: str = "models/vosk-model-small-en-us-0.15"
    voice_input_device: int = -1
    voice_sample_rate: int = 16000
    voice_timeout: int = 10
    speak_enabled: bool = False
    speech_rate: int = 0
    speech_volume: int = 100
    voice_debug_enabled: bool = True
    voice_debug_path: str = "data/voice_debug.jsonl"
    memory_path: str = "data/memory.json"
    notes_path: str = "data/notes.md"
    tasks_path: str = "data/tasks.json"
    outbox_path: str = "data/outbox.json"
    history_enabled: bool = True
    history_path: str = "data/history.jsonl"
    action_audit_enabled: bool = True
    action_audit_path: str = "data/action_audit.jsonl"
    voice_action_audit_enabled: bool = True
    voice_action_audit_path: str = "data/voice_action_audit.jsonl"
    persona_path: str = "config/persona.txt"
    aliases_path: str = "config/aliases.json"

    def summary(self) -> str:
        return (
            f"assistant_name={self.assistant_name}, "
            f"model={self.model}, "
            f"use_llm={self.use_llm}, "
            f"num_gpu={self.num_gpu}, "
            f"voice_enabled={self.voice_enabled}, "
            f"voice_input_device={self.voice_input_device}, "
            f"voice_sample_rate={self.voice_sample_rate}, "
            f"voice_timeout={self.voice_timeout}, "
            f"speak_enabled={self.speak_enabled}, "
            f"speech_rate={self.speech_rate}, "
            f"speech_volume={self.speech_volume}, "
            f"voice_debug_enabled={self.voice_debug_enabled}, "
            f"voice_debug_path={self.voice_debug_path}, "
            f"memory_path={self.memory_path}, "
            f"notes_path={self.notes_path}, "
            f"tasks_path={self.tasks_path}, "
            f"outbox_path={self.outbox_path}, "
            f"history_enabled={self.history_enabled}, "
            f"history_path={self.history_path}, "
            f"action_audit_enabled={self.action_audit_enabled}, "
            f"action_audit_path={self.action_audit_path}, "
            f"voice_action_audit_enabled={self.voice_action_audit_enabled}, "
            f"voice_action_audit_path={self.voice_action_audit_path}, "
            f"persona_path={self.persona_path}, "
            f"aliases_path={self.aliases_path}"
        )


SETTING_TYPES = {
    "assistant_name": str,
    "model": str,
    "use_llm": bool,
    "num_gpu": int,
    "voice_enabled": bool,
    "voice_model_path": str,
    "voice_input_device": int,
    "voice_sample_rate": int,
    "voice_timeout": int,
    "speak_enabled": bool,
    "speech_rate": int,
    "speech_volume": int,
    "voice_debug_enabled": bool,
    "voice_debug_path": str,
    "memory_path": str,
    "notes_path": str,
    "tasks_path": str,
    "outbox_path": str,
    "history_enabled": bool,
    "history_path": str,
    "action_audit_enabled": bool,
    "action_audit_path": str,
    "voice_action_audit_enabled": bool,
    "voice_action_audit_path": str,
    "persona_path": str,
    "aliases_path": str,
}


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> AssistantSettings:
    settings_path = Path(path)
    if not settings_path.exists():
        return AssistantSettings()

    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Invalid settings JSON: {settings_path}") from exc
    except OSError as exc:
        raise SettingsError(f"Could not read settings: {settings_path}") from exc

    if not isinstance(raw, dict):
        raise SettingsError("Settings file must contain a JSON object.")

    allowed = set(AssistantSettings.__dataclass_fields__)
    filtered: dict[str, Any] = {key: value for key, value in raw.items() if key in allowed}
    return AssistantSettings(**filtered)


def save_settings(
    settings: AssistantSettings,
    path: str | Path = DEFAULT_SETTINGS_PATH,
) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(asdict(settings), indent=2) + "\n",
        encoding="utf-8",
    )


def parse_setting_value(key: str, value: str) -> str | int | bool:
    if key not in SETTING_TYPES:
        raise SettingsError(f"Unknown setting: {key}")

    expected_type = SETTING_TYPES[key]
    clean_value = value.strip()

    if expected_type is bool:
        lowered = clean_value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise SettingsError(f"Setting '{key}' expects true or false.")

    if expected_type is int:
        try:
            return int(clean_value)
        except ValueError as exc:
            raise SettingsError(f"Setting '{key}' expects an integer.") from exc

    if not clean_value:
        raise SettingsError(f"Setting '{key}' cannot be empty.")
    return clean_value


def update_setting(
    settings: AssistantSettings,
    key: str,
    value: str,
) -> AssistantSettings:
    parsed_value = parse_setting_value(key, value)
    return replace(settings, **{key: parsed_value})


def update_settings_file(
    updates: dict[str, str],
    path: str | Path = DEFAULT_SETTINGS_PATH,
) -> AssistantSettings:
    settings = load_settings(path)
    for key, value in updates.items():
        settings = update_setting(settings, key, value)
    save_settings(settings, path)
    return settings

